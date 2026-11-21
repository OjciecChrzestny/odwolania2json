"""Segmentacja pism według ról i pierwszej zaskarżonej czynności."""
import re
from dataclasses import dataclass

from .model import FLAGS, empty
from .operations import DATE, apply_fields, normalize


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
        return [opening.group(labeled, "entity")]

    introduction = opening.after(patterns["header"]).stripped()
    return [introduction.after(patterns["representing"]).stripped()]


def signatures(document, patterns):
    signing = document.before(patterns["acceptance"])
    headings = list(re.finditer(patterns["signed_heading"], signing.text, FLAGS))
    owners = [(match.start(), normalize(match["entity"], "text").casefold()) for match in headings]
    for match in re.finditer(patterns["signature"], signing.text, FLAGS):
        owner = next((name for start, name in reversed(owners) if start < match.start()), None)
        yield owner, signing.group(match, 1)


def add_principal(result, config, block, signers, separate):
    patterns = config["patterns"]
    block = block.stripped()
    firm = block.find(patterns["sole_trader"])
    name_block = block.slice(firm.end()) if firm else block
    name = name_block.before(patterns["name_end"]).stripped()
    value = normalize(name.text.strip(" ,;:"), "text")
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
        if separate and (not owner or owner.rstrip(".") != value.casefold().rstrip(".")):
            continue
        items.append({})
        result.put((*path, "podpisujacy", len(items) - 1, "imie_nazwisko"),
                   normalize(signer.text, "text"), signer.offset, "podpis_w_sekcji_mocodawcy")


def power_of_attorney(result, config):
    patterns = config["patterns"]
    document = Fragment(result.document.text)
    blocks = principal_blocks(document, config)
    signers = list(signatures(document, patterns))
    for block in blocks:
        add_principal(result, config, block, signers, len(blocks) > 1)

    grant = document.find(patterns["grant"])
    label = document.find(patterns["counsel_label"])
    opening = [document.slice(match.end()) for match in (label, grant) if match]
    acceptance = document.find(patterns["acceptance"])
    if acceptance:
        opening.append(document.slice(acceptance.end()))
    for proposal in opening:
        scope = proposal.stripped().before(patterns["counsel_end"])
        matches = list(re.finditer(patterns["counsel"], scope.text, FLAGS))
        if not matches:
            continue
        for index, match in enumerate(matches):
            path = append_item(result, config, "pelnomocnicy")
            put_match(result, (*path, "imie_nazwisko"), scope, match, 1, "imię_w_sekcji_umocowania")
            end = matches[index + 1].start() if index + 1 < len(matches) else None
            fields(result, config["counsel_fields"], scope.slice(match.end(), end), path)
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


def classify_reason(fragment, config):
    matches = []
    for priority, rule in enumerate(config["reasons"]["rules"]):
        match = fragment.find(rule["pattern"])
        if match:
            matches.append((fragment.offset + match.start(), priority, rule["id"]))
    if not matches:
        return None
    location, _, reason_id = min(matches)
    return reason_id, location


def first_allegation(body, patterns):
    intro = body.find(patterns["allegation_list_intro"])
    if intro:
        scope = body.slice(intro.end()).before(patterns["section_end"])
        bullets = list(re.finditer(patterns["enumeration"], scope.text, FLAGS))
        prelude = scope.text[:bullets[0].start()] if bullets else ""
        prelude = re.sub(r"(?im)^[ \t]*Strona \d+(?: z \d+)?[ \t]*$", "", prelude)
        if bullets and not prelude.strip():
            end = bullets[1].start() if len(bullets) > 1 else None
            return scope.slice(bullets[0].end(), end), "pierwsza_czynność_z_listy"
    formal = body.find(patterns["formal_first"])
    if formal:
        scope = body.slice(formal.end()).before(patterns["formal_next"]).before(patterns["section_end"])
        return scope, "pierwszy_numerowany_zarzut"
    return None, None


def challenged_action(result, config, body):
    patterns = config["patterns"]
    hint = body.find(patterns["action_line"])
    allegation, selector = first_allegation(body, patterns)
    # Dla zarzutu z nagłówkiem kolejny wiersz zwykle opisuje podstawę prawną i skutki.
    # Typ czynności jest ustalany z nagłówka, bez przenoszenia motywów z uzasadnienia.
    decision = allegation
    if allegation and selector == "pierwszy_numerowany_zarzut":
        decision = allegation.slice(0, min(len(allegation.text), 240)).before(
            r"(?m):[ \t]*$|,[ \t\n]*tj\.")
    chosen = classify_reason(decision, config) if decision else None
    if hint and not chosen:
        # W starszej redakcji fakt poprzedzający zarzut opisuje kwestionowaną czynność.
        hint_scope = body.group(hint)
        chosen = classify_reason(hint_scope, config)
        if chosen:
            allegation, selector = hint_scope, "czynność_wprowadzająca_pierwszy_zarzut"

    prefix = ("OdwolanieKIO",)
    if chosen:
        reason_id, location = chosen
        record = {"page": result.document.page(location), "rule": selector, "fallback": False}
        action_date = allegation.find(patterns["action_date"])
        if action_date:
            put_match(result, (*prefix, "czynnosc_dzien"), allegation, action_date, "date",
                      "data_pierwszej_zaskarżonej_czynności", "date")
        elif hint and (classify_reason(body.group(hint), config) or (None,))[0] == reason_id:
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
    return {"first_allegation": record}


def appeal(result, config):
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
    fields(result, config["header_fields"], cover)
    body = document.after(patterns["header"])
    return challenged_action(result, config, body.slice(0, 8500))


BUILDERS = {"power_of_attorney": power_of_attorney, "appeal": appeal}
