"""Assign observed Polish account numbers to the parties identified on a page."""
import re
from collections import Counter, defaultdict

from .transfer import ACCOUNT

PAYER = "z_rachunku"
PAYEE = "na_rachunek"
FOLD = str.maketrans("ąćęłńóśźż", "acelnoszz")
LABEL = re.compile(
    r"\b(?:(?P<owner>(?:rachunek|dane)\s+wlasciciela|rachunek wlasny)"
    r"|(?P<other>(?:dane|rachunek)\s+(?:kontrahenta|beneficjenta\s*/\s*\w+))"
    r"|(?P<payer>(?:rachunek\s*:?\s*(?:winien|obciazany|nadawcy|zleceniodawcy|platnika)"
    r"|z rachunku|dane\s+(?:platnika|zleceniodawcy)"
    r"|(?:dane\s+)?(?:nadawca|nadawcy|platnik|zleceniodawca)|payer|sender|debtor))"
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

OWN_ACCOUNT_SECTION = re.compile(r"^dane (?:o |do |dotyczace )?rachunku(?: bankowego)?[ \t:|.]*$")
FOREIGN_ACCOUNT_SECTION = re.compile(
    r"^(?:dane (?:do|dla|dotyczace) zwrotu|rachunek do zwrotu|sekcja zwrotu"
    r"|kopia (?:dla|do)|kopie otrzymuje|rozdzielnik)\b"
)
TITLE_LINE = re.compile(r"^(?:tytul|title|tytulem)\b")
SOURCE_ACCOUNT = re.compile(r"^przelew z rachunku(?:[ :|/-]+szczegoly (?:transakcji|operacji))?[ :|.-]*$")
NUMBER_FIELD = re.compile(r"^(?:numer|nr) rachunku[ \t:|]+(?P<literal>(?:pl[ \t]*)?[0-9][0-9 \t]*)$")
WRAP_START = re.compile(r"PL ?([0-9]{2}(?: [0-9]{4}){1,5})", re.I)
WRAP_END = re.compile(r"[0-9]{4}(?: [0-9]{4}){0,4}")


def fold(text):
    return text.lower().translate(FOLD)


def nrb_digits(value):
    if isinstance(value, str):
        digits = value.removeprefix("PL")
        if re.fullmatch(r"[0-9]{26}", digits):
            return digits
    return None


def valid_nrb(value):
    digits = nrb_digits(value)
    return digits is not None and int(digits[2:] + "2521" + digits[:2]) % 97 == 1


def number_forms(text):
    """Read complete groups and remember the literal country prefix separately."""
    for match in RUN.finditer(text):
        value = "".join(match[1].split())
        if valid_nrb(value):
            yield value, match[0][:2].upper() == "PL"
        elif len(value) == 52:
            pair = [(hit, "".join(hit["nrb"].split())) for hit in ACCOUNT.finditer(match[0])]
            if len(pair) == 2 and "".join(digits for _, digits in pair) == value:
                for hit, digits in pair:
                    if valid_nrb(digits):
                        yield digits, hit[0][:2].upper() == "PL"


def numbers(text):
    return [digits for digits, _ in number_forms(text)]


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


def account_layout(rows, positions, *, generic_owner=False, require_counterparty_section=False):
    """Yield role sections and their column boundary when both sides are supported."""
    folded = [fold(row) for row in rows]
    direction_rows = (
        [line for line in folded if not TITLE_LINE.search(line.strip(" \t|"))]
        if require_counterparty_section else folded
    )
    page = "\n".join(direction_rows)
    debit, credit = bool(DEBIT.search(page)), bool(CREDIT.search(page))
    owner = (PAYER if debit else PAYEE) if debit != credit else None
    active, divider, expiry = [], None, -1
    counterparty_section = False
    for i, line in enumerate(folded):
        if STOP.search(line.strip(" \t|")) or i > expiry:
            active, divider = [], None
            counterparty_section = False
        marks = headings(line)
        if not marks and generic_owner and owner and OWN_ACCOUNT_SECTION.fullmatch(line.strip()):
            marks = [("owner", 0, len(line))]
        if marks:
            neutral_marks = [line[start:end] for label, start, end in marks if label == "other"]
            counterparty_section = bool(neutral_marks) and (counterparty_section or
                                      any(mark.startswith("dane ") for mark in neutral_marks))
            active = [
                direct_role(label, owner)
                if label != "other" or not require_counterparty_section or counterparty_section else None
                for label, _, _ in marks
            ]
            expiry = i + 5
            divider = None
            if positions and len(active) == 2 and set(active) == {PAYER, PAYEE}:
                divider = column_at(positions[i], marks[1][1])
        yield i, marks, active, divider


def column_words(words, divider):
    return tuple(w for w in words if w.x < divider), tuple(w for w in words if w.x >= divider)


def wrapped_nrb(upper, lower):
    """Read an explicitly marked Polish IBAN wrapped into two aligned lines."""
    if not upper or not lower:
        return None
    first, second = upper[0], lower[0]
    if (abs(first.x - second.x) > min(first.height, second.height) / 2
            or second.middle - first.middle > first.height + second.height):
        return None
    start = WRAP_START.fullmatch(" ".join(w.text for w in upper))
    finish = WRAP_END.fullmatch(" ".join(w.text for w in lower))
    if start and finish:
        value = (start[1] + finish[0]).replace(" ", "")
        if valid_nrb(value):
            return value


def detached_account_cells(words):
    """An explicit account field in its own visual cell, beside unrelated fields."""
    breaks = [i for i, (left, right) in enumerate(zip(words, words[1:]), 1)
              if right.x - left.x - left.width > 2 * max(left.height, right.height)]
    for start, stop in zip(breaks, (*breaks[1:], len(words))):
        text = " ".join(word.text for word in words[start:stop])
        marks = headings(fold(text))
        if len(marks) == 1:
            label, _, end = marks[0]
            tail = text[end:].lstrip()
            if label in ("payer", "payee") and tail.startswith((":", "|")):
                yield direct_role(label, None), number_forms(tail)


def source_account_fields(rows, folded):
    """Read the standalone number field immediately below a source-account heading."""
    for i, heading in enumerate(folded[:-1]):
        if not SOURCE_ACCOUNT.fullmatch(heading.strip()):
            continue
        following = next((j for j in range(i + 1, len(rows)) if rows[j].strip()), None)
        if following is None:
            continue
        match = NUMBER_FIELD.fullmatch(folded[following].strip())
        if match:
            raw = rows[following].strip()
            yield from number_forms(raw[match.start("literal"):])


class AccountObservations(dict):
    """Keep the existing role-to-digits mapping and add spelling evidence."""

    def __init__(self, values, prefixed):
        super().__init__(values)
        self.prefixed = frozenset(prefixed)


def account_observations(rows, positions=None):
    """Return all role-supported numbers. Different candidates signal ambiguity."""
    observed = defaultdict(set)
    prefixed = set()
    # A generic account section identifies the account of the statement owner
    # only when a separate counterparty section and an explicit direction coexist.
    folded = [fold(row) for row in rows]
    boundary = next((i for i, line in enumerate(folded)
                     if FOREIGN_ACCOUNT_SECTION.search(line.lstrip(" \t|:.-"))), len(rows))
    rows, folded = rows[:boundary], folded[:boundary]
    if positions is not None:
        positions = positions[:boundary]
    generic_owner = any(label == "other" and line[start:end].startswith("dane ")
                        for line in folded for label, start, end in headings(line))

    def observe(role, values):
        for value, has_prefix in values:
            observed[role].add(value)
            if has_prefix:
                prefixed.add((role, value))

    layout = account_layout(rows, positions, generic_owner=generic_owner, require_counterparty_section=True)
    for i, marks, active, divider in layout:
        row = rows[i]
        if len(marks) == 2:
            # A line can have explicit labels and values in both cells.
            for which, (role, (_, _, end)) in enumerate(zip(active, marks)):
                stop = marks[which + 1][1] if which + 1 < len(marks) else len(row)
                if role:
                    observe(role, number_forms(row[end:stop]))
                label_start = marks[which][1]
                if divider is None or i + 2 >= len(rows) or "rachun" not in fold(row[label_start:end]):
                    continue
                following = positions[i + 1:i + 3]
                if any(word.x < divider < word.x + word.width for words in following for word in words):
                    continue
                upper, lower = (column_words(words, divider)[which] for words in following)
                value = wrapped_nrb(upper, lower)
                if value:
                    observe(role, ((value, True),))
            continue
        if positions and not marks:
            detached = list(detached_account_cells(positions[i]))
            if detached:
                for role, forms in detached:
                    observe(role, forms)
                continue
        if len(active) == 1 and active[0]:
            observe(active[0], number_forms(row))
        elif len(active) == 2 and all(active) and active[0] != active[1]:
            if divider is not None:
                if any(word.x < divider < word.x + word.width and re.search(r"[0-9]", word.text)
                       for word in positions[i]):
                    continue
                for role, cell in zip(active, column_words(positions[i], divider)):
                    observe(role, number_forms(" ".join(w.text for w in cell)))
            else:
                pair = list(number_forms(row))
                if len(pair) == 2:
                    for role, form in zip(active, pair):
                        observe(role, (form,))
    observe(PAYER, source_account_fields(rows, folded))
    return AccountObservations(observed, prefixed)


def apply_accounts(result, pages, *, scanned=()):
    """A checksum verifies the digits. A separate label must support their role."""
    bank = result.data["przelew_bankowy"]
    by_role = {PAYER: defaultdict(set), PAYEE: defaultdict(set)}
    prefixes = Counter()
    ocr_pages = {page["page"] for page in (result.document.scan_quality or {}).get("pages", ())
                 if page.get("source") == "ocr"}
    singleton_readings = Counter()
    ambiguous = set()
    for page, evidence in pages:
        for role, values in evidence.items():
            other = PAYEE if role == PAYER else PAYER
            for value in values:
                by_role[role][value].add(page)
                if len(values) > 1:
                    ambiguous.add((role, value, page))
                elif value not in evidence.get(other, ()):
                    singleton_readings[role, value, page] += 1
        prefixes.update((role, value, page) for role, value in getattr(evidence, "prefixed", ()))
    # A single view can put a field in the wrong column. Discard only this
    # cross-role conflict once independent readings agree on its actual side.
    def agreed(role, value, sources):
        return any(singleton_readings[role, value, page] >= 2 for page in sources)

    for role, other in ((PAYER, PAYEE), (PAYEE, PAYER)):
        for value in by_role[role].keys() & by_role[other].keys():
            sources = by_role[role][value]
            if (agreed(other, value, by_role[other][value]) and not agreed(role, value, sources)
                    and not any((role, value, page) in ambiguous for page in sources)):
                del by_role[role][value]

    for role, candidates in by_role.items():
        path = "przelew_bankowy." + role
        other = PAYEE if role == PAYER else PAYER
        previous = bank[role]
        old_page = result.evidence.get(path, {}).get("page")
        protected = previous is not None and old_page not in scanned
        if len(candidates) == 1:
            digits, sources = next(iter(candidates.items()))
            if digits not in by_role[other]:
                # Repeated scan observations can establish the prefix. A
                # literal on the already assigned OCR page can also refine the
                # spelling of that same account without changing its digits.
                prefixed_sources = [
                    page for page in sources
                    if prefixes[role, digits, page]
                    and (page not in scanned or prefixes[role, digits, page] >= 2
                         or (page == old_page and page in ocr_pages and previous == digits))
                ]
                value = "PL" + digits if prefixed_sources else digits
                page = min(prefixed_sources or sources)
                preserves_ocr_spelling = (
                    value == "PL" + digits and previous == digits and page == old_page and page in ocr_pages
                )
                if not protected or preserves_ocr_spelling:
                    if value != previous:
                        result.put(("przelew_bankowy", role), value, result.document.starts[page - 1][0],
                                   "nrb_mod97_i_rola_na_stronie")
                continue
        if protected:
            continue
        if old_page in scanned and (candidates or not valid_nrb(previous) or nrb_digits(previous) in by_role[other]):
            bank[role] = None
            result.evidence.pop(path, None)
