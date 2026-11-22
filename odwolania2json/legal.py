"""Segmentacja pism według ról i pierwszej zaskarżonej czynności."""
import re
from dataclasses import dataclass

from .model import FLAGS, empty
from .operations import DATE, apply_fields, normalize
from .podpisy import add_confirmed_signatures


@dataclass(frozen=True)
class Fragment:
    text: str
    offset: int = 0

    def slice(self, start=0, end=None):
        return Fragment(self.text[start:end], self.offset + start)

    def find(self, pattern):
        return re.search(pattern.replace("<DATE>", DATE), self.text, FLAGS)

    def group(self, match, name=0):
        return self.slice(*match.span(name))

    def before(self, pattern):
        match = self.find(pattern)
        return self.slice(0, match.start()) if match else self

    def after(self, pattern):
        match = self.find(pattern)
        return self.slice(match.end()) if match else self

    def stripped(self):
        start = len(self.text) - len(self.text.lstrip())
        return self.slice(start, len(self.text.rstrip()))


def append_item(result, config, key):
    items = result.data[key]
    items.append(empty(config["schema"][key][0]))
    return key, len(items) - 1


def put_match(result, path, fragment, match, group, rule, operation="text"):
    result.put(path, normalize(match[group], operation), fragment.offset + match.start(group), rule)


def fields(result, definitions, fragment, path=()):
    apply_fields(result, definitions, fragment.text, fragment.offset, path)


def principal_blocks(document, config):
    patterns = config["patterns"]
    grant = document.find(patterns["grant"])
    opening = document.slice(0, grant.start()) if grant else document
    consortium = opening.find(patterns["consortium"])
    if consortium:
        members = opening.group(consortium, "members")
        return [members.group(match, "entity")
                for match in re.finditer(patterns["member"], members.text, FLAGS)]

    labeled = opening.find(patterns["principal_block"])
    if labeled:
        return [opening.group(labeled, "entity").before(patterns["principal_representation"])]

    introduction = opening.after(patterns["header"]).stripped()
    label = introduction.find(patterns["principal_label"])
    if label and label.start() == 0:
        return [introduction.slice(label.end()).before(patterns["principal_representation"])]
    entity = introduction.after(patterns["representing"]).before(patterns["principal_representation"])
    return [entity.stripped()]


def signatures(document, patterns):
    signing = document.before(patterns["acceptance"])
    owners = list(re.finditer(patterns["signed_heading"], signing.text, FLAGS))
    labels = list(re.finditer(patterns["signature_label"], signing.text, FLAGS))
    signers = {signing.offset + match.start(1): signing.group(match, 1)
               for match in re.finditer(patterns["signature"], signing.text, FLAGS)}
    headings = sorted([*owners, *labels], key=lambda match: match.start())
    for index, heading in enumerate(headings):
        stop = headings[index + 1].start() if index + 1 < len(headings) else None
        block = signing.slice(heading.end(), stop).stripped()
        for line in block.text.split("\n"):
            if "\f" in line:
                break
            if not line.strip() or re.fullmatch(patterns["signature_office"], line, FLAGS):
                block = block.slice(len(line) + 1)
                continue
            match = re.fullmatch(patterns["signature_entry"], line, FLAGS)
            if not match:
                break
            signer = block.group(match, "name")
            signers[signer.offset] = signer
            block = block.slice(len(line) + 1)

    for offset, signer in sorted(signers.items()):
        owner = next((match["entity"] for match in reversed(owners)
                      if signing.offset + match.end() <= offset), None)
        yield normalize(owner, "text") if owner else None, signer


def principal_name(text, patterns):
    value = normalize(text.strip(" ,;:"), "text")
    # Zachowaj litery i interpunkcję skrótu, gdy odczyt skleił jego człony.
    return re.sub(patterns["company_suffix"], r"\1 \2 \3", value, flags=FLAGS)


def add_principal(result, config, block, signers, separate):
    patterns = config["patterns"]
    block = block.stripped()
    firm = block.find(patterns["sole_trader"])
    name_block = block.slice(firm.end()) if firm else block
    name = name_block.before(patterns["name_end"]).stripped()
    value = principal_name(name.text, patterns)
    if not value:
        return
    path = append_item(result, config, "mocodawca")
    physical = bool(block.find(patterns["physical"]))
    kind = "osoba_fizyczna" if physical else "osoba_prawna"
    name_key = "imie_nazwisko" if physical and not firm else "nazwa"
    result.put((*path, "data", name_key), value, name.offset, "nazwa_w_sekcji_mocodawcy")
    if firm:
        person = block.find(patterns["sole_trader_person"])
        if person:
            put_match(result, (*path, "data", "imie_nazwisko"), block, person, 1,
                      "osoba_prowadząca_działalność")
    result.put((*path, "data", "typ"), kind, name.offset, "typ_mocodawcy")
    fields(result, config["principal_fields"], block, path)

    items = result.data[path[0]][path[1]]["podpisujacy"]
    for owner, signer in signers:
        if owner:
            if principal_name(owner, patterns).casefold().rstrip(".") != value.casefold().rstrip("."):
                continue
        elif separate:
            continue
        items.append({})
        result.put((*path, "podpisujacy", len(items) - 1, "imie_nazwisko"),
                   normalize(signer.text, "text"), signer.offset, "podpis_w_sekcji_mocodawcy")


def counsel_entries(scope, patterns):
    """Rozpoznaje ciąg nazwisk we fragmencie wskazującym umocowanych."""
    remaining = scope
    entries = []
    needs_role_marker = False
    while match := remaining.find(patterns["counsel_entry"]):
        has_role_marker = bool(match["title"] or match["point"] or match["details"])
        if needs_role_marker and not has_role_marker:
            break
        entries.append((remaining.group(match, "name"), remaining.group(match, "details")))
        remaining = remaining.slice(match.end())
        separator = remaining.find(patterns["counsel_separator"])
        if not separator:
            break
        # Po opisanej pozycji sam nowy wiersz nie dowodzi, że kolejny tekst to pełnomocnik.
        needs_role_marker = has_role_marker and separator[0].endswith("\n")
        remaining = remaining.slice(separator.end())
    if entries:
        return entries

    # Starsze układy zawierają wprowadzenie przed wymienieniem radców lub adwokatów.
    matches = list(re.finditer(patterns["counsel"], scope.text, FLAGS))
    return [
        (scope.group(match, 1), scope.slice(match.end(), next_match.start() if next_match else None))
        for match, next_match in zip(matches, [*matches[1:], None])
    ]


def power_of_attorney(result, config):
    patterns = config["patterns"]
    first_page = min((item["page"] for item in result.signals), default=1)
    document = Fragment(result.document.text).slice(result.document.starts[first_page - 1][0])
    blocks = principal_blocks(document, config)
    signers = list(signatures(document, patterns))
    for block in blocks:
        add_principal(result, config, block, signers, len(blocks) > 1)
    add_confirmed_signatures(result, config, document, blocks, result.document.ocr_layout_tsv)

    appointment = document.before(patterns["acceptance"])
    grant = appointment.find(patterns["grant"])
    if grant:
        # Nie otwieraj sekcji pełnomocników ponownie w stopce podpisowej.
        body = appointment.slice(grant.end()).before(patterns["signature_label"]).before(patterns["signed_heading"])
        appointment = appointment.slice(0, grant.end() + len(body.text))
    for key in ("counsel_label", "grant"):
        marker = appointment.find(patterns[key])
        if not marker:
            continue
        scope = appointment.slice(marker.end()).stripped().before(patterns["counsel_end"]).stripped()
        entries = counsel_entries(scope, patterns)
        if not entries:
            continue
        for name, details in entries:
            path = append_item(result, config, "pelnomocnicy")
            result.put((*path, "imie_nazwisko"), normalize(name.text, "text"), name.offset,
                       "imię_w_sekcji_umocowania")
            fields(result, config["counsel_fields"], details, path)
        break
    return {}


def add_party(result, config, key, role, block, multiple):
    patterns = config["patterns"]
    block = block.stripped()
    counsel = block.find(patterns["counsel_section"]) if key == "Odwolujacy" else None
    entity = block.slice(0, counsel.start()) if counsel else block
    entity = entity.after(patterns["leader"]).before(patterns["partner"]).stripped()
    if not entity.text:
        return
    path = append_item(result, config, key)
    name = entity.before(patterns["entity_end"]).stripped()
    result.put((*path, "nazwa"), normalize(name.text.rstrip(" ,;"), "text"),
               name.offset, "nazwa_w_sekcji_strony")
    fields(result, config["party_fields"], entity, path)

    if key == "Zamawiajacy" and multiple:
        lead = re.search(r"\blider\b|\bprowadzący\b", role["qualifier"], FLAGS)
        result.put((*path, "prowadzacy_postepowanie"), int(bool(lead)), block.offset,
                   "rola_współzamawiającego")
    if key == "Odwolujacy":
        result.put((*path, "przez-pelnomocnika"), int(bool(counsel)), block.offset,
                   "wzmianka_o_reprezentacji")
        if counsel:
            mandate = block.slice(counsel.end()).stripped()
            person = mandate.find(patterns["counsel"])
            if person:
                put_match(result, (*path, "pelnomocnik", "imie_nazwisko"),
                          mandate, person, 1, "pierwszy_wskazany_pełnomocnik")
            fields(result, config["counsel_fields"], mandate, path)


def match_reason(fragment, config):
    matches = []
    for priority, rule in enumerate(config["reasons"]["rules"]):
        match = fragment.find(rule["pattern"])
        if match:
            matches.append((fragment.offset + match.start(), priority, rule["id"]))
    if not matches:
        return None
    location, _, reason_id = min(matches)
    return reason_id, location


def reason_evidence(fragment, config):
    """Rozpoznaje przedmiot zaskarżenia z pominięciem wyraźnie wyłączonych czynności."""
    patterns = config["patterns"]
    verb = patterns.get("challenge_verb")
    basis = patterns.get("legal_basis_start")
    legal_basis = basis and fragment.find(basis)
    if legal_basis:
        # Łącznik w nawiasie lub cytacie należy do przywołania przepisu.
        connector = next((match for match in re.finditer(
            patterns["legal_basis_action"], fragment.text, FLAGS) if match["connector"]), None)
        if connector:
            fragment = fragment.slice(connector.end())
        else:
            assertion = fragment.find(verb) if verb else None
            if not assertion:
                return None, None, None
            fragment = fragment.slice(assertion.start())
    markers = list(re.finditer(verb, fragment.text, FLAGS)) if verb else []
    if not markers:
        return match_reason(fragment, config), fragment if legal_basis else None, fragment
    remaining = list(fragment.text)
    excluded = []
    first_assertion = None
    for index, marker in enumerate(markers):
        stop = markers[index + 1].start() if index + 1 < len(markers) else None
        clause = fragment.slice(marker.end(), stop).before(patterns["challenge_clause_end"])
        if marker["disclaimed"]:
            end = marker.end() + len(clause.text)
            remaining[marker.start():end] = " " * (end - marker.start())
            excluded.append((marker.start(), end))
        else:
            if first_assertion is None and clause.text.strip():
                first_assertion = clause
            chosen = match_reason(clause, config)
            if chosen:
                return chosen, clause, clause
    available = Fragment("".join(remaining), fragment.offset)
    chosen = match_reason(available, config)
    if not chosen:
        return None, available, first_assertion

    # Fragment udostępniany odbiorcy odpowiada rzeczywistym pozycjom w PDF.
    position = chosen[1] - fragment.offset
    start = max((end for _, end in excluded if end <= position), default=0)
    stop = min((begin for begin, _ in excluded if begin > position), default=len(fragment.text))
    return chosen, available, fragment.slice(start, stop)


def classify_reason(fragment, config):
    return reason_evidence(fragment, config)[0]


def first_allegation(body, patterns):
    body = body.before(patterns["formal_next"])
    formal = body.find(patterns["formal_first"])
    assertion_pattern = patterns.get("allegation_assertion")
    assertion = body.find(assertion_pattern) if assertion_pattern else None
    marker = min((match for match in (formal, assertion) if match),
                 key=lambda match: match.start(), default=None)
    before_marker = body.slice(0, marker.start()) if marker else body
    for intro in re.finditer(patterns["allegation_list_intro"], before_marker.text, FLAGS):
        if intro.groupdict().get("filing_context") and before_marker.group(intro, "filing_context").find(
                patterns["section_end"]):
            continue
        scope = before_marker.slice(intro.end()).before(patterns["section_end"])
        bullets = iter(re.finditer(patterns["enumeration"], scope.text, FLAGS))
        first = next(bullets, None)
        if not first or not re.fullmatch(r"\s*\(?(?:1|I)[.)]\s*", first.group(), FLAGS):
            continue
        prelude = re.sub(r"(?im)^[ \t]*Strona \d+(?: z \d+)?[ \t]*$", "", scope.text[:first.start()])
        if not prelude.strip():
            second = next(bullets, None)
            return scope.slice(first.end(), second.start() if second else None), "pierwsza_czynność_z_listy"

    if marker is None:
        return None, None
    scope = body.slice(marker.end()).before(patterns["section_end"])
    if marker is assertion:
        return scope.before(assertion_pattern), "pierwszy_zarzut_wprost"
    return scope, "pierwszy_numerowany_zarzut"


def challenged_action(result, config, body, *, capture_decision=False):
    patterns = config["patterns"]
    hint = body.slice(0, 8500).before(patterns["formal_next"]).find(patterns["action_line"])
    allegation, selector = first_allegation(body, patterns)
    details = {}
    if capture_decision:
        details["allegation_structure"] = ({"page": result.document.page(allegation.offset), "rule": selector}
                                          if allegation is not None else None)
    # Dla zarzutu z nagłówkiem kolejny wiersz zwykle opisuje podstawę prawną i skutki.
    # Typ czynności jest ustalany z nagłówka, bez przenoszenia motywów z uzasadnienia.
    decision = allegation
    verb = patterns.get("challenge_verb")
    explicit = allegation.find(verb) if allegation and verb else None
    basis = patterns.get("legal_basis_start")
    legal_basis = allegation is not None and basis and allegation.find(basis)
    contextual_hint = not (explicit or legal_basis or selector == "pierwszy_zarzut_wprost")
    if allegation and selector == "pierwszy_numerowany_zarzut" and not (explicit or legal_basis):
        decision = allegation.slice(0, min(len(allegation.text), 240)).before(
            r"(?m):[ \t]*$|,[ \t\n]*tj\.")
    chosen, date_scope, excerpt = reason_evidence(decision, config) if decision else (None, None, None)
    if hint and not chosen and contextual_hint:
        # W starszej redakcji fakt poprzedzający zarzut opisuje kwestionowaną czynność.
        hint_scope = body.group(hint)
        chosen = classify_reason(hint_scope, config)
        if chosen:
            allegation, excerpt = hint_scope, hint_scope
            selector = "czynność_wprowadzająca_pierwszy_zarzut"

    prefix = ("OdwolanieKIO",)
    if chosen:
        reason_id, location = chosen
        record = {"page": result.document.page(location), "rule": selector, "fallback": False}
        dated = date_scope if date_scope is not None else allegation
        action_date = dated.find(patterns["action_date"])
        if action_date:
            put_match(result, (*prefix, "czynnosc_dzien"), dated, action_date, "date",
                      "data_pierwszej_zaskarżonej_czynności", "date")
        elif hint and contextual_hint and (classify_reason(body.group(hint), config) or (None,))[0] == reason_id:
            put_match(result, (*prefix, "czynnosc_dzien"), body, hint, "date",
                      "data_z_jednoznacznego_opisu_tej_czynności", "date")
    else:
        location = allegation.offset if allegation else body.offset
        reason_id = config["reasons"]["fallback"]
        record = {"page": result.document.page(location),
                  "rule": "brak_jednoznacznej_reguły_czynności", "fallback": True}

    result.put((*prefix, "czynnosc_powod_id"), reason_id, location, record["rule"])
    description = config["reasons"]["descriptions"][str(reason_id)]
    result.put((*prefix, "czynnosc_opis"), description, location, "opis_kanoniczny_id")
    details["first_allegation"] = record
    if capture_decision and excerpt is not None and any(char.isalnum() for char in excerpt.text):
        details["decision_fragment"] = excerpt
        source_offset = location if chosen else excerpt.offset
        details["decision_source"] = {"page": result.document.page(source_offset), "rule": selector}
    return details


def appeal(result, config, *, capture_decision=False):
    patterns = config["patterns"]
    document = Fragment(result.document.text)
    first_page = document.before(r"\f")
    cover = document.before(patterns["body_start"])
    if len(cover.text) > 5500:
        cover = cover.slice(0, min(len(first_page.text), 5500))
    date = first_page.find(patterns["filing_date"]) or first_page.find(patterns["standalone_date"])
    if date:
        put_match(result, ("OdwolanieKIO", "data"), first_page, date, "date", "data_nagłówka", "date")
        if "city" in date.groupdict():
            put_match(result, ("OdwolanieKIO", "miejscowosc"), first_page, date, "city",
                      "miejscowość_przy_dacie")
    roles = list(re.finditer(patterns["role"], cover.text, FLAGS))
    buyers = sum(match["role"].casefold() == "zamawiający" for match in roles)
    for index, role in enumerate(roles):
        end = roles[index + 1].start() if index + 1 < len(roles) else None
        key = "Zamawiajacy" if role["role"].casefold() == "zamawiający" else "Odwolujacy"
        block = cover.slice(role.end(), end).before(patterns["role_end"])
        add_party(result, config, key, role, block, buyers > 1)
    from .appeal_parties import refine_appeal_parties

    refine_appeal_parties(result, config, cover)
    fields(result, config["header_fields"], cover)
    body = document.after(patterns["header"])
    return challenged_action(result, config, body, capture_decision=capture_decision)


BUILDERS = {"power_of_attorney": power_of_attorney, "appeal": appeal}
