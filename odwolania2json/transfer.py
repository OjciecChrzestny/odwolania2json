"""Read labelled bank-transfer tables when PDF/OCR flattens their columns."""
import re
from dataclasses import dataclass
from math import isfinite

from .bank_scan import labelled_numbers
from .model import FLAGS
from .operations import DATE, apply_fields, normalize
from .transfer_title import TITLE, apply_transfer_title

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


def number_candidates(lines):
    candidates = {}
    for row, priority, token in labelled_numbers(tuple(line for _, line in lines)):
        offset, _ = lines[row]
        candidates.setdefault(token.key, []).append((priority, token.value, offset + token.start))
    for key, hits in candidates.items():
        rank = max(priority for priority, _, _ in hits)
        best = [(value, pos) for priority, value, pos in hits if priority == rank]
        if len({value for value, _ in best}) == 1:
            yield key, rank, *best[0]


def amount_and_date(result, lines):
    bank = result.data["przelew_bankowy"]
    for key, rank, value, pos in number_candidates(lines):
        path = ("przelew_bankowy", key)
        rule = result.evidence.get(".".join(path), {}).get("rule")
        if bank[key] is None or (rank == 3 and rule == "data_zaksięgowania"):
            result.put(path, value, pos, "kwota_i_data_w_kolumnach")


def primary_number_fallback(result, primary):
    """Use a primary observation on the page that established the transfer class."""
    variant = result.document
    if primary is None or primary is variant:
        return
    confirming_pages = {signal.get("page") for signal in result.signals}
    bank = result.data["przelew_bankowy"]
    for page, text in enumerate(primary.text.split("\n\f\n")[:-1], 1):
        if page not in confirming_pages:
            continue
        for key, priority, value, _ in number_candidates(page_lines(text, 0)):
            existing = result.evidence.get("przelew_bankowy." + key, {})
            other_page_table = (existing.get("rule") == "kwota_i_data_w_kolumnach"
                                and existing.get("page") not in confirming_pages)
            if priority == 3 and (bank[key] is None or other_page_table):
                rule = "kwota_w_głównym_odczycie" if key == "kwota" else "data_w_głównym_odczycie"
                result.put(("przelew_bankowy", key), value, variant.starts[page - 1][0], rule)


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


def reference_matches(document, lines):
    """Yield labelled transaction IDs together with their source positions."""
    for i, (start, line) in enumerate(lines):
        label = REF.match(line)
        if not label:
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
            gap = document.text[start + len(line):next_pos]
            if gap.count("\\n") <= 2:
                value_pos, first = next_pos, next_line
        value = reference_value(first, bank_reference=bool(label["bank"]))
        if value is None:
            continue
        rule = REF_DAILY_RULE if label["daily"] else REF_RULE
        yield value, value_pos, rule


def reference_number(result, lines):
    path = ("przelew_bankowy", "numer_transakcji")
    field = ".".join(path)
    evidence = result.evidence.get(field)
    # A daily sequence is useful only when there is no full transaction reference.
    if evidence and evidence["rule"] != REF_DAILY_RULE:
        return
    for value, value_pos, rule in reference_matches(result.document, lines):
        if rule == REF_DAILY_RULE and evidence:
            continue
        result.put(path, value, value_pos, rule)
        if rule == REF_RULE:
            return
        evidence = result.evidence[field]


LINE = re.compile(r"^[ \t]*([^\s\f][^\n\f]*)", re.M)
PARAGRAPH_BREAK = re.compile(r"\n(?:[ \t]*\n)+")
REFERENCE_HEADING = re.compile(
    r"^(?!(?:opis|tytuł|title|description|uwagi|wzmianka|historia|archiwum)\b)"
    r"(?:(?:[^\W\d_]+[ \t]+){0,4}(?:operacja|transakcja|przelew|operation|transaction|transfer)"
    r"|(?:szczegóły|potwierdzenie) (?:operacji|transakcji|przelewu))"
    r"[ \t]+(?:(?:nr|id)[.:]?[ \t]+)?(?P<reference>[A-Za-z0-9][A-Za-z0-9_./-]*)[ \t:]*$",
    re.I,
)
AMOUNT_PATH = ("przelew_bankowy", "kwota")
AMOUNT_FIELD = ".".join(AMOUNT_PATH)
REFERENCE_FIELD = "przelew_bankowy.numer_transakcji"


@dataclass(frozen=True)
class AmountObservation:
    value: float
    start: int
    end: int
    operation: str


def page_lines(text, offset):
    return [(offset + match.start(1), match[1].rstrip()) for match in LINE.finditer(text)]


def paragraph_ranges(text):
    start = 0
    for separator in PARAGRAPH_BREAK.finditer(text):
        yield start, separator.start()
        start = separator.end()
    yield start, len(text)


def observed_amounts(page, offset, lines, patterns):
    amounts = {}
    for pattern, operation in patterns:
        for match in pattern.finditer(page):
            value = normalize(match[1], operation)
            if value is not None and isfinite(value):
                start, end = match.span(1)
                amounts.setdefault(start, AmountObservation(value, offset + start, offset + end, operation))
    for row, _, token in labelled_numbers(tuple(line for _, line in lines)):
        if token.key == "kwota":
            start, line = lines[row]
            # The contract expresses the absolute amount. Exclude a debit sign
            # from a span that may later be checked with the money normalizer.
            pos = start + token.start + int(line[token.start] in "-−+")
            amounts.setdefault(pos - offset, AmountObservation(token.value, pos, start + token.end, "money"))
    return list(amounts.values())


def block_references(document, lines):
    explicit = {ref.casefold() for ref, _, rule in reference_matches(document, lines) if rule == REF_RULE}
    headings = set()
    for _, line in lines:
        match = REFERENCE_HEADING.fullmatch(line)
        if match and (reference := reference_value(match["reference"], bank_reference=False)):
            headings.add(reference.casefold())
    role = any(ROLE.match(line) or any(pattern.search(line) for pattern in DIRECTION.values())
               for _, line in lines)
    return explicit, headings, role


def resolve_amount_evidence(result, config, pages):
    if result.data["przelew_bankowy"]["kwota"] is None:
        return
    current = result.data["przelew_bankowy"]["numer_transakcji"]
    ref_evidence = result.evidence.get(REFERENCE_FIELD, {})
    ref_page = ref_evidence.get("page")
    class_pages = {signal.get("page") for signal in result.signals}
    anchored = ref_evidence.get("rule") == REF_RULE and ref_page in class_pages and bool(current)
    target = current.casefold() if anchored else None
    patterns = [
        (re.compile(rule["pattern"].replace("<DATE>", DATE), FLAGS), rule.get("operation", "money"))
        for rule in config["fields"].get(AMOUNT_FIELD, ())
    ]
    observations = []
    for page_start, page_number, page, lines in pages:
        amounts = observed_amounts(page, page_start, lines, patterns)
        if page_number == ref_page and target:
            # The primary labelled ID must be unambiguous in the confirming page's
            # local block. A reference encountered only on an attachment is not an anchor.
            for left, right in paragraph_ranges(page):
                explicit, _, _ = block_references(
                    result.document, page_lines(page[left:right], page_start + left))
                if target in explicit:
                    anchored = explicit == {target}
                    break
            else:
                anchored = False
        if not amounts:
            continue
        for left, right in paragraph_ranges(page):
            local = [amount for amount in amounts if page_start + left <= amount.start < page_start + right]
            if not local:
                continue
            explicit, headings, role = block_references(
                result.document, page_lines(page[left:right], page_start + left))
            references = explicit | headings
            supported = explicit or (headings if role else set())
            match = len(local) == 1 and references == {target} and target in supported
            observations.extend((amount, match, references) for amount in local)

    if not observations:
        return
    if len(observations) == 1:
        # A unique amount retains its span only when its block has no
        # contradictory operation IDs, even if one of them matches the cover.
        _, _, references = observations[0]
        if len(references) <= 1 and (not anchored or not references or target in references):
            return
    linked = [amount for amount, match, _ in observations if match]
    if anchored and len(linked) == 1:
        amount = linked[0]
        result.put(AMOUNT_PATH, amount.value, amount.start, "kwota_powiazana_z_id_operacji",
                   span_end=amount.end, operation=amount.operation)
    else:
        # The numeric output remains provisional. Clear all location and text claims.
        result.evidence[AMOUNT_FIELD] = {
            "kind": "conflict", "precision": "unavailable", "page": None, "source": None,
            "rule": "niejednoznaczne_powiazanie_kwoty_z_operacja",
        }


def transfer(result, config):
    # OCR sometimes inserts extra blank lines before missing values.
    missing = {path: rules for path, rules in config["fields"].items()
               if result.data["przelew_bankowy"][path.rsplit(".", 1)[1]] is None}
    title_rules = config["fields"].get(TITLE, ())
    if any(rule.get("title_layout") for rule in title_rules):
        missing.pop(TITLE, None)
        apply_transfer_title(result, title_rules)
    for key in ROLES:
        path = "przelew_bankowy." + key
        if path in missing:
            # Compacting blank lines can merge two independent parties.
            # The section reader below checks how many accounts the heading covers.
            missing[path] = [rule for rule in missing[path] if rule["name"] != "rachunek_w_sekcji_roli"]
    if missing:
        text = re.sub(r"\n(?:[ \t]*\n)+", lambda m: " " * (len(m[0]) - 1) + "\n", result.document.text)
        apply_fields(result, missing, text)
    pages = []
    for page_start, page_number in result.document.starts:
        end = (result.document.starts[page_number][0] if page_number < len(result.document.starts)
               else len(result.document.text))
        page = result.document.text[page_start:end].removesuffix("\n\f\n")
        lines = page_lines(page, page_start)
        pages.append((page_start, page_number, page, lines))
        account_tables(result, lines)
        amount_and_date(result, lines)
        reference_number(result, lines)
    resolve_amount_evidence(result, config, pages)
    return {}
