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
REF = re.compile(
    r"^(?:(?P<bank>Referencj[ae] banku|Bank reference(?: number)?)"
    r"|(?P<daily>Dzienny (?:numer|nr) transakcji)"
    r"|(?:Transaction|Transfer) (?:reference(?: number)?|ID|number)"
    r"|Reference number|Nr ref\.?"
    r"|(?:Numer|Nr|Identyfikator|ID) (?:transakcji|operacji|referencyjny|przelewu|referencji))"
    r"(?:[ \t]+operacji)?(?=[ \t:.\-]|$)",
    re.I,
)
REF_BANK_QUALIFIER = re.compile(r"^[ \t]+w[ \t]+[^:\d]*\b(?:banku|bank)\b[^:\d]*:", re.I)
REF_NEXT_FIELD = re.compile(
    r"[ \t]+(?:[|;][ \t]*)?(?:Data|Date|Kwota|Amount|Rachunek|Account|Status|Tytuł|Title|Opis|"
    r"(?:Nr|Numer|ID|Identyfikator)[ \t]+(?:dokumentu|wydruku|potwierdzenia))\b",
    re.I,
)
REF_VALUE = re.compile(r"(?=[A-Za-z0-9_./-]*[0-9])[A-Za-z0-9][A-Za-z0-9_./-]*")
REF_GROUPED_DIGITS = re.compile(r"[0-9]+(?:[ \t]+[0-9]+)+")
REF_ACCOUNT = re.compile(r"(?:PL)?[0-9]{24,26}", re.I)
REF_IBAN = re.compile(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", re.I)
REF_RULE = "numer_referencyjny_transakcji"
REF_DAILY_RULE = "dzienny_numer_transakcji"
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


def reference_value(text, *, bank_reference):
    value = normalize(text, "identifier")
    if not value or DATE_VALUE.fullmatch(value):
        return None
    # Bank references can contain visual spacing between groups of digits.
    if bank_reference and REF_GROUPED_DIGITS.fullmatch(value):
        value = value.replace(" ", "")
    if not REF_VALUE.fullmatch(value):
        return None
    compact = re.sub(r"[./_-]", "", value).upper()
    if REF_ACCOUNT.fullmatch(compact):
        return None
    if REF_IBAN.fullmatch(compact):
        reordered = compact[4:] + compact[:4]
        digits = "".join(str(ord(ch) - ord("A") + 10) if ch.isalpha() else ch for ch in reordered)
        if int(digits) % 97 == 1:
            return None
    return value


def reference_number(result, lines):
    path = ("przelew_bankowy", "numer_transakcji")
    field = ".".join(path)
    evidence = result.evidence.get(field)
    # A daily sequence is useful only when there is no full transaction reference.
    if evidence and evidence["rule"] != REF_DAILY_RULE:
        return
    for i, (start, line) in enumerate(lines):
        label = REF.match(line)
        if not label or (label["daily"] and evidence):
            continue
        tail = line[label.end():]
        qualifier = REF_BANK_QUALIFIER.match(tail)
        if qualifier:
            tail = tail[qualifier.end():]
        value_pos = start + len(line) - len(tail)
        first = tail.lstrip(" \\t:.-")
        value_pos += len(tail) - len(first)
        if first:
            following_field = REF_NEXT_FIELD.search(first)
            if following_field:
                first = first[:following_field.start()]
        elif i + 1 < len(lines):
            next_pos, next_line = lines[i + 1]
            gap = result.document.text[start + len(line):next_pos]
            if gap.count("\\n") <= 2:
                value_pos, first = next_pos, next_line
        value = reference_value(first, bank_reference=bool(label["bank"]))
        if value is None:
            continue
        rule = REF_DAILY_RULE if label["daily"] else REF_RULE
        result.put(path, value, value_pos, rule)
        if rule == REF_RULE:
            return
        evidence = result.evidence[field]


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
