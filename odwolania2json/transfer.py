"""Read labelled bank-transfer tables when PDF/OCR flattens their columns."""
import re

from .operations import DATE, apply_fields, normalize

ROLES = {
    "z_rachunku": r"rachunek (?:winien|obciążany|nadawcy|zleceniodawcy|płatnika)|z rachunku|nadawc[ay]|płatnik|zleceniodawca|sender|payer|debtor",
    "na_rachunek": r"rachunek (?:ma|uznawany|odbiorcy|beneficjenta)|na rachunek|adresat przelewu|odbiorc[ay]|beneficjent|recipient|beneficiary|payee|creditor",
}
ROLE = re.compile(r"\b(?:" + "|".join(f"(?P<{k}>{v})" for k, v in ROLES.items()) + r")\b", re.I)
ACCOUNT = re.compile(
    r"(?<![\w])(?:PL[ \t]*)?(?P<nrb>[0-9]{26}|[0-9]{2}(?:[ \t]+[0-9]{4}){6}"
    r"|[0-9]{2}[ \t]+[0-9]{8}(?:[ \t]+[0-9]{4}){4}|[0-9]{10}(?:[ \t]+[0-9]{4}){4})(?![\w])",
    re.I,
)
OWN = re.compile(r"^(?:Account (?:info(?:rmation)?|details)|Dane rachunku|Rachunek własny)\s*:?$", re.I)
STOP = re.compile(r"^(?:Szczegóły|Transaction details|Kwota|Wartość|Data|Tytuł|Opis|Amount|Title|Status|Nr ref)\b", re.I)
MONEY = re.compile(r"(?<![\d.,])(?:\d{1,3}(?:[ .]\d{3})+|\d+)[,.]\d{2}(?![\d.,])")
DATE_VALUE = re.compile(DATE, re.I)
REF = re.compile(r"^(?:Nr ref\.?|Numer referencyjny|Identyfikator (?:operacji|transakcji))(?=\W|$)", re.I)
REF_VALUE = re.compile(r"(?<![\w/.-])(?=[\w/.-]*\d)[a-zA-Z0-9][a-zA-Z0-9_./-]{2,}(?![\w/.-])")
DIRECTION = {
    "z_rachunku": re.compile(r"\b(?:przelew (?:wychodzący|wychodzacy)|outgoing (?:bank )?transfer)\b|^(?:Transfer amount|Amount|Kwota(?: operacji)?)[ \t]*:?[ \t]+(?:PLN[ \t]*)?[-−][ \t]*[0-9]", re.I | re.M),
    "na_rachunek": re.compile(r"\b(?:przelew przychodzący|incoming (?:bank )?transfer)\b", re.I),
}


def roles_in_header(line):
    matches = list(ROLE.finditer(line))
    if not matches:
        return ()
    # Exclude names, addresses and narrative text which merely mention a party.
    remainder = ROLE.sub("", line)
    if not re.fullmatch(r"(?:[ \t():/|.,-]|\b(?:dane|strona|winien|ma|account|details)\b)*", remainder, re.I):
        return ()
    return tuple(dict.fromkeys(match.lastgroup for match in matches))


def account_tables(result, lines):
    headers = [roles_in_header(text) for _, text in lines]
    owner = None
    explicit = set()
    for i, (offset, line) in enumerate(lines):
        roles = headers[i]
        own = OWN.fullmatch(line)
        if not (roles or own):
            continue
        explicit.update(roles)
        found = []
        for j in range(i + 1, min(i + 9, len(lines))):
            start, following = lines[j]
            next_role = ROLE.match(following)
            if (headers[j] or OWN.fullmatch(following) or STOP.match(following)
                    or next_role and next_role.lastgroup not in roles):
                break
            matches = list(ACCOUNT.finditer(following))
            if matches:
                if len(roles) == 2 and len(matches) != 2:
                    # Only a shared row preserves the link between the two columns.
                    found = []
                    break
                found.extend((normalize(m["nrb"], "digits"), start + m.start("nrb")) for m in matches)
        if own and len(found) == 1:
            owner = found[0]
        elif len(roles) == 1 and len({account for account, _ in found}) > 1:
            role = roles[0]
            key = "przelew_bankowy." + role
            evidence = result.evidence.get(key, {})
            if evidence.get("rule") == "rachunek_w_sekcji_roli" and evidence["page"] == result.document.page(offset):
                result.data["przelew_bankowy"][role] = None
                del result.evidence[key]
        elif len(roles) == len(found):
            for role, (account, pos) in zip(roles, found):
                if result.data["przelew_bankowy"][role] is None:
                    result.put(("przelew_bankowy", role), account, pos, "rachunek_pod_nagłówkiem_roli")
    if owner and explicit == set(ROLES):
        # A negative debit or an explicit transfer direction identifies the statement owner's side.
        page_text = "\n".join(line for _, line in lines)
        directions = [role for role, pattern in DIRECTION.items() if pattern.search(page_text)]
        if len(directions) == 1:
            role = directions[0]
            if result.data["przelew_bankowy"][role] is None:
                result.put(("przelew_bankowy", role), *owner, "rachunek_własny_i_kierunek")


def amount_and_date(result, lines):
    for i, (_, line) in enumerate(lines[:-1]):
        if not (re.search(r"\b(?:Kwota|Wartość)\b", line, re.I)
                and re.search(r"\bData (?:transakcji|realizacji|operacji|wykonania)\b", line, re.I)):
            continue
        pos, values = lines[i + 1]
        dates = list(DATE_VALUE.finditer(values))
        if len(dates) != 1:
            continue
        date = dates[0]
        # A date such as 12.03.2024 must not become the amount.
        money = list(MONEY.finditer(values[:date.start()] + " " * len(date[0]) + values[date.end():]))
        if len(money) != 1:
            continue
        for key, match, operation in (("data_operacji", date, "date"), ("kwota", money[0], "money")):
            if result.data["przelew_bankowy"][key] is None:
                result.put(("przelew_bankowy", key), normalize(match[0], operation),
                           pos + match.start(), "kwota_i_data_w_kolumnach")


def reference_number(result, lines):
    for i, (start, line) in enumerate(lines):
        label = REF.match(line)
        if not label:
            continue
        value = result.data["przelew_bankowy"]["numer_transakcji"]
        if value and any(ch.isdigit() for ch in value):
            return
        tail = line[label.end():]
        tokens = list(REF_VALUE.finditer(tail))
        if len(tokens) == 1:
            token = tokens[0]
            result.put(("przelew_bankowy", "numer_transakcji"), token[0].rstrip("."),
                       start + label.end() + token.start(), "identyfikator_w_wierszu_referencji")
        elif i and not re.search(r"\w", tail):
            pos, previous = lines[i - 1]
            if REF_VALUE.fullmatch(previous) and not ACCOUNT.fullmatch(previous) and any(ch.isalpha() for ch in previous):
                result.put(("przelew_bankowy", "numer_transakcji"), previous,
                           pos, "identyfikator_nad_etykietą")
        return


def transfer(result, config):
    # Keep paragraph breaks in titles found on the first pass. OCR sometimes
    # inserts extra blank lines between a label and its otherwise missing value.
    missing = {path: rules for path, rules in config["fields"].items()
               if result.data["przelew_bankowy"][path.rsplit(".", 1)[1]] is None}
    for key in ROLES:
        path = "przelew_bankowy." + key
        if path in missing:
            # Compacting blank lines can merge two independent parties.
            # The section reader below checks how many accounts the heading covers.
            missing[path] = [rule for rule in missing[path] if rule["name"] != "rachunek_w_sekcji_roli"]
    if missing:
        text = re.sub(r"\n(?:[ \t]*\n)+", lambda m: " " * (len(m[0]) - 1) + "\n", result.document.text)
        apply_fields(result, missing, text)
    for page_start, page_number in result.document.starts:
        end = (result.document.starts[page_number][0] if page_number < len(result.document.starts)
               else len(result.document.text))
        page = result.document.text[page_start:end]
        lines = [(page_start + match.start(1), match[1].rstrip())
                 for match in re.finditer(r"^[ \t]*([^\s\f][^\n\f]*)", page, re.M)]
        account_tables(result, lines)
        amount_and_date(result, lines)
        reference_number(result, lines)
    return {}
