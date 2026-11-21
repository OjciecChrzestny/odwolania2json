"""Assign observed Polish account numbers to the parties identified on a page."""
import re
from collections import defaultdict

from .transfer import ACCOUNT

PAYER = "z_rachunku"
PAYEE = "na_rachunek"
FOLD = str.maketrans("ąćęłńóśźż", "acelnoszz")
LABEL = re.compile(
    r"\b(?:(?P<owner>(?:rachunek|dane)\s+wlasciciela|rachunek wlasny)"
    r"|(?P<other>(?:dane|rachunek)\s+(?:kontrahenta|beneficjenta\s*/\s*\w+))"
    r"|(?P<payer>(?:rachunek\s*:?\s*(?:winien|obciazany|nadawcy|zleceniodawcy|platnika)"
    r"|z rachunku|(?:dane\s+)?(?:nadawca|nadawcy|platnik|zleceniodawca)|payer|sender|debtor))"
    r"|(?P<payee>(?:rachunek\s*:?\s*(?:ma|uznawany|odbiorcy|beneficjenta)"
    r"|na rachunek|(?:dane\s+)?(?:odbiorca|odbiorcy|beneficjent)|payee|beneficiary|creditor)))\b"
)
STOP = re.compile(
    r"^(?:szczegoly|tytul|kwota|data|adres do|saldo|bank (?:posredniczacy|korespondent)"
    r"|(?:numer |nr )?(?:rachun\w*|kont\w*) (?:vat|technicz\w*|do (?:oplat|zwrotu))"
    r"|referencj\w*|(?:numer|nr|identyfikator) (?:operacji|transakcji)|w rozliczeniach|opis|title|amount)\b"
)
DEBIT = re.compile(r"\b(?:wychodz[ae]c[ay]|obciazenie|outgoing transfer)\b|^\s*kwota(?: operacji)?\s*:?\s*[-−]\s*\d", re.M)
CREDIT = re.compile(r"\b(?:przychodz[ae]c[ay]|uznanie|incoming transfer)\b")
RUN = re.compile(r"(?<![\w*])(?:PL[ \t]*)?([0-9]+(?:[ \t]+[0-9]+)*)(?![\w*])", re.I)


def fold(text):
    return text.lower().translate(FOLD)


def valid_nrb(value):
    return (isinstance(value, str) and re.fullmatch(r"[0-9]{26}", value) is not None
            and int(value[2:] + "2521" + value[:2]) % 97 == 1)


def numbers(text):
    found = []
    for m in RUN.finditer(text):
        value = "".join(m[1].split())
        if valid_nrb(value):
            found.append(value)
        elif len(value) == 52:
            # Two flattened columns may place both complete NRBs on one line.
            pair = ["".join(hit["nrb"].split()) for hit in ACCOUNT.finditer(m[0])]
            if len(pair) == 2 and "".join(pair) == value:
                found.extend(n for n in pair if valid_nrb(n))
    return found


def headings(text):
    matches = list(LABEL.finditer(text))
    if not matches or text[:matches[0].start()].strip(" \t:()/|.,-[]") not in ("", "nr", "numer", "konto", "strona"):
        return []
    result = []
    for match in matches:
        if not result or match.lastgroup != result[-1][0]:
            result.append((match.lastgroup, match.start(), match.end()))
    return result


def direct_role(label, owner):
    if label == "owner":
        return owner
    if label == "other":
        return {PAYER: PAYEE, PAYEE: PAYER}.get(owner)
    return {"payer": PAYER, "payee": PAYEE}[label]


def column_at(words, offset):
    """Locate a heading in the same joined TSV text used by the label matcher."""
    consumed = 0
    for word in words:
        consumed += len(word.text) + 1
        if consumed > offset:
            return word.x - word.height / 2
    return None


def account_observations(rows, positions=None):
    """Return all role-supported numbers. Different candidates signal ambiguity."""
    folded = [fold(row) for row in rows]
    page = "\n".join(folded)
    debit, credit = bool(DEBIT.search(page)), bool(CREDIT.search(page))
    owner = (PAYER if debit else PAYEE) if debit != credit else None
    observed = defaultdict(set)
    active, divider, expiry = [], None, -1
    for i, (row, line) in enumerate(zip(rows, folded)):
        if STOP.search(line.strip(" \t|")) or i > expiry:
            active, divider = [], None
        marks = headings(line)
        if marks:
            active = [direct_role(label, owner) for label, _, _ in marks]
            expiry = i + 5
            divider = column_at(positions[i], marks[1][1]) if positions and len(marks) == 2 else None
            if len(marks) == 2:
                # A line can have explicit labels and values in both cells.
                for which, (role, (_, _, end)) in enumerate(zip(active, marks)):
                    stop = marks[which + 1][1] if which + 1 < len(marks) else len(row)
                    if role:
                        observed[role].update(numbers(row[end:stop]))
                continue
        if len(active) == 1 and active[0]:
            observed[active[0]].update(numbers(row))
        elif len(active) == 2 and all(active) and active[0] != active[1]:
            if divider is not None:
                left = " ".join(w.text for w in positions[i] if w.x < divider)
                right = " ".join(w.text for w in positions[i] if w.x >= divider)
                for role, cell in zip(active, (left, right)):
                    observed[role].update(numbers(cell))
            else:
                pair = numbers(row)
                if len(pair) == 2:
                    for role, value in zip(active, pair):
                        observed[role].add(value)
    return {key: values for key, values in observed.items() if values}


def apply_accounts(result, pages, *, scanned=()):
    """A checksum verifies the digits. A separate label must support their role."""
    bank = result.data["przelew_bankowy"]
    by_role = {PAYER: defaultdict(set), PAYEE: defaultdict(set)}
    for page, evidence in pages:
        for role, values in evidence.items():
            for value in values:
                by_role[role][value].add(page)
    for role, candidates in by_role.items():
        path = "przelew_bankowy." + role
        previous = bank[role]
        old_page = result.evidence.get(path, {}).get("page")
        if previous is not None and old_page not in scanned:
            continue
        if len(candidates) == 1:
            value, sources = next(iter(candidates.items()))
            page = min(sources)
            if value != previous:
                result.put(("przelew_bankowy", role), value, result.document.starts[page - 1][0],
                           "nrb_mod97_i_rola_na_stronie")
        elif old_page in scanned and (candidates or not valid_nrb(previous) or
                                      previous in by_role[PAYEE if role == PAYER else PAYER]):
            bank[role] = None
            result.evidence.pop(path, None)
