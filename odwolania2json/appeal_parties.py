"""Ground appeal parties and their procedural representative in scanned headers."""
from dataclasses import dataclass
import re
from statistics import median
from unicodedata import combining, normalize as unicode_normalize

from .bank_scan import word_rows
from .legal import Fragment
from .model import FLAGS, empty
from .operations import apply_fields, normalize

APPELLANT, BUYER = "Odwolujacy", "Zamawiajacy"
ROLE = re.compile(
    r"(?:^[ \t]*(?:„[ \t]*(?=[^\n\f:]+:[ \t]*$))?(?:\d{1,2}[.)][ \t]*)?|(?<=[ \t|])(?=(?:odwo[łl]uj|zamawiaj)))"
    r"(?P<role>odwo[łl]uj[ąa]c[yae]|zamawiaj[ąa]c[yae])"
    r"(?P<qualifier>[ \t]*[–—-][ \t]*(?:lider|prowadz[ąa]cy|partner)\b[^:\n\f]{0,38})?"
    r"[ \t]*(?:[:：][ \t]*|[–—][ \t]+|(?=$))", FLAGS,
)
END = re.compile(
    r"^[ \t]*(?:ODWO[ŁL]ANIE[ \t]*:?$|Dotyczy\b|Wnosz[ęe] (?:o |odwo[łl]anie)|"
    r"Zarzuty\b|Uzasadnienie\b|Przedmiot zam[óo]wienia\b|Za[łl][ąa]czniki\b|"
    r"(?P<distribution>Do wiadomo[śs]ci\b|Rozdzielnik\b|Kopi[eę][ \t]+otrzymuj\w*\b|"
    r"Kopia[ \t]+dla\b|Otrzymuj[ąa]\b)|Stopka\b|Podpis\b|Cytat\b)", FLAGS,
)
REPRESENTATION = re.compile(
    r"\b(?:(?:reprezentowan[yaeią]|dzia[łl]aj[ąa]c[yae]|zast[ęe]powan[yaeią])\s+przez\b"
    r"(?:[ \t,;]+pe[łl]nomocnik(?:a|ów)?)?|przez[ \t,;]+pe[łl]nomocnik(?:a|ów)?|"
    r"pe[łl]nomocnik(?:[ \t]+(?:procesowy|odwo[łl]uj[ąa]cego|wykonawcy))?"
    r"(?=[ \t]*[:：]|[ \t\n]+(?:adw|radc|r[. ]))|"
    r"prz[eę]z\b[^\n\f]{0,28}(?=(?:[ \t]*\n)+[ \t]*(?:radc|adw|r\.)))"
    r"[ \t\n]*[:：]?[ \t\n]*", FLAGS,
)
PROFESSION = re.compile(
    r"^(?:adw(?:okat\w*)?\.?|radc(?:a|ę|y)[ \t]+prawn(?:y|ego)|r\.?[ \t]*p(?:r)?\.)[ \t\n]+",
    re.I,
)
ADDRESS = re.compile(
    r"(?:^|[ \t,;])['’]?(?:ul(?:ica)?\.?[ \t]+|al\.?[ \t]+|pl\.[ \t]+|"
    r"z siedzib[ąa]\b|(?:KRS|NIP|REGON|telefon)[ \t]*[:. ]|(?:e[- ]?mail|tel|fax)[ \t]*[:.]|"
    r"\d{2}-\d{3}\b|https?://)|^[ \t]*(?:adres|siedziba|kontakt)\b", FLAGS,
)
LEGAL_FORM = re.compile(
    r"(?<!\w)(?:sp\.?[ \t]*z[ \t]+o\.?[ \t]*o\.?|sp[oó][łl]ka[ \t]+z[ \t]+ograniczon[ąa]"
    r"[ \t]+odpowiedzialno[śs]ci[ąa]|sp[oó][łl]ka[ \t]+akcyjna|s\.[ \t]*a\.|"
    r"sp\.?[ \t]*j\.|sp\.?[ \t]*k\.|s\.k\.a\.)(?=\W|$)", re.I,
)
OFFICE = re.compile(r"(?<!\w)(?:kancelari[aeęi]|sp[oó][łl]ka[ \t]+partnerska)\b", re.I)
CONTACT_BREAK = re.compile(r"^[ \t]*(?:sygnatura|przetarg|post[ęe]powanie|adresat|"
                           r"op[łl]ata|dane do faktury|strona \d+|znak sprawy)\b", FLAGS)
MAIL = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9-]+(?:\.[A-Z0-9-]+)*\.[A-Z]{2,}"
                  r"(?![\w-])", re.I)
DIRECT_MAIL = re.compile(r"\b(?:e[- ]?mail|poczta elektroniczna)[ \t]*[:：]?[ \t]*$", re.I)
MAIL_ROW = re.compile(r"^[ \t]*(?:e[- ]?mail|poczta elektroniczna)[ \t]*[:：][ \t]*(?P<value>[^\n\f]+)", FLAGS)
OBSCURED_AT = re.compile(r"\([ \t]*a\)?", re.I)
MAIL_DOTS = re.compile(r"[ \t]*\.[ \t]*")
PERSON = re.compile(
    r"(?P<name>[A-ZĄĆĘŁŃÓŚŹŻ][^\W\d_]+(?:[-’'][A-ZĄĆĘŁŃÓŚŹŻ][^\W\d_]+)?"
    r"[ \t\n]+[A-ZĄĆĘŁŃÓŚŹŻ][^\W\d_]+(?:[-’'][A-ZĄĆĘŁŃÓŚŹŻ][^\W\d_]+)?)"
)
NOT_PERSON = re.compile(r"\b(?:kancelaria|radca|adwokat|ulica|pełnomocnik|kontakt|adres|nr)\b", re.I)
SEPARATORS = " \t\n,;:|–—-"
LEADING_NOISE = SEPARATORS + "_."
COMPANY_OCR_FORM = re.compile(r"(?<!\w)(sp\.)[ \t]+z[ \t]+[o0]\.[o0]\.(?!\w)", re.I)
TRADE_NAME = re.compile(r"\bprowadz[ąa]c[yae][ \t]+dzia[łl]alno[śs][ćc][ \t]+gospodarcz[ąa]"
                        r"[ \t]+pod[ \t]+firm[ąa][ \t\n]*[:：]?[ \t\n]*", re.I)
CONSORTIUM = re.compile(r"^[ \t\n]*konsorcjum(?:[ \t]+wykonawc[óo]w)?[ \t]*:[ \t]*\n"
                        r"[ \t]*(?:\d{1,2}[.)][ \t]*)?", re.I)
LEAD = re.compile(r"[ \t]+\([ \t]*lider(?:[ \t]+konsorcjum)?[ \t]*\)", re.I)
JOINT_BUYERS = re.compile(r"^[ \t\n]*zamawiaj[ąa]cy[ \t]+wsp[óo]lnie[ \t]+udzielaj[ąa]c[ya]"
                          r"[ \t]+zam[óo]wienia[ \t]*:[ \t\n]*", re.I)
LEAD_BUYER = re.compile(r"^[ \t–—-]*zamawiaj[ąa]cy[ \t]+prowadz[ąa]cy[ \t]+"
                         r"post[ęe]powanie[ \t]*[:：]?[ \t]*$", FLAGS)
ENUMERATION = re.compile(r"^[ \t\n]*\d{1,2}[.)][ \t]*")


@dataclass(frozen=True)
class Section:
    role: str
    qualifier: str
    block: Fragment
    layout: bool = False
    joint_group: bool = False
    distribution: Fragment | None = None


def _role(label):
    return APPELLANT if label.casefold().startswith("odwo") else BUYER


def _sections(header):
    labels = []
    for label in ROLE.finditer(header.text):
        line_start = header.text.rfind('\n', 0, label.start()) + 1
        if label.start() != line_start and (not labels or labels[-1].start() != line_start):
            continue
        labels.append(label)
    for index, label in enumerate(labels):
        end = labels[index + 1].start() if index + 1 < len(labels) else len(header.text)
        raw = header.slice(label.end(), end)
        boundary = END.search(raw.text)
        block = raw.slice(0, boundary.start()) if boundary else raw
        distribution = raw.slice(boundary.start()) if boundary and boundary["distribution"] else None
        role = _role(label["role"])
        paired = _joint_buyers(block) if role == BUYER else None
        if paired:
            yield from paired
        else:
            yield Section(role, label["qualifier"] or "", block, distribution=distribution)


def _joint_buyers(block):
    header = JOINT_BUYERS.match(block.text)
    leader = LEAD_BUYER.search(block.text)
    if not header or not leader or header.end() >= leader.start():
        return None
    parts = [_trim(block.slice(header.end(), leader.start())), _trim(block.slice(leader.end()))]
    if not all(_name(part) for part in parts):
        return None
    return [Section(BUYER, "", part, joint_group=True) for part in parts]


def _column_sections(tsv):
    """Use geometry only when both role headings occupy distinct columns."""
    if not tsv:
        return []
    try:
        rows = word_rows(tsv)
    except ValueError:
        return []
    for index, row in enumerate(rows):
        text = " ".join(word.text for word in row)
        matches = list(ROLE.finditer(text))
        if len(matches) != 2 or _role(matches[0]["role"]) == _role(matches[1]["role"]):
            continue
        second = len(text[:matches[1].start("role")].split())
        if not 0 < second < len(row):
            continue
        right_start = row[second].x
        if right_start - row[0].x < 6 * median(word.height for word in row):
            continue
        # Words to the left of the right heading belong to the first column.
        # Any line crossing the boundary invalidates this interpretation.
        border = right_start - median(word.height for word in row)
        columns = [[], []]
        for following in rows[index:index + 18]:
            if any(word.x < border < word.x + word.width for word in following):
                break
            line = " ".join(word.text for word in following)
            boundary = END.match(line)
            if boundary and not boundary["distribution"]:
                break
            for side in (0, 1):
                parts = [word.text for word in following if int(word.x >= border) == side]
                if parts:
                    columns[side].append(" ".join(parts))
        sections = []
        for column in columns:
            matched = list(_sections(Fragment("\n".join(column))))
            if len(matched) != 1:
                break
            item = matched[0]
            sections.append(Section(item.role, item.qualifier, item.block, layout=True,
                                    distribution=item.distribution))
        if len(sections) == 2 and all(_name(item.block) for item in sections):
            return sections
    return []


def _trim(block):
    start = len(block.text) - len(block.text.lstrip(LEADING_NOISE))
    stop = len(block.text.rstrip(SEPARATORS))
    return block.slice(start, max(start, stop))


def _name(block):
    block = _trim(block)
    registered = TRADE_NAME.search(block.text.split("\f", 1)[0])
    if registered and registered.start() <= 100:
        block = _trim(block.slice(registered.end()))
    consortium = CONSORTIUM.match(block.text)
    if consortium:
        block = block.slice(consortium.end())
        leader = LEAD.search(block.text.split("\n", 1)[0])
        if not leader:
            return None
        block = block.slice(0, leader.start())
    number = ENUMERATION.match(block.text)
    if number:
        block = _trim(block.slice(number.end()))
    if not block.text or block.text[0] in '„”"«(':
        return None
    stop = ADDRESS.search(block.text)
    text = block.text[:stop.start()] if stop else block.text
    lines = text.splitlines()
    if not lines or CONTACT_BREAK.match(lines[0]) or not re.search(r"[^\W\d_]{2}", lines[0]):
        return None
    end = len(lines[0])
    # A wrapped legal form makes continuation observable. A later address or
    # a second capitalized line alone is insufficient.
    if len(lines) > 1 and not CONTACT_BREAK.match(lines[1]):
        paired = text[:end + 1 + len(lines[1])]
        if not LEGAL_FORM.search(lines[0]) and LEGAL_FORM.search(paired.replace("\n", " ")):
            end = len(paired)
    fragment = _trim(block.slice(0, end))
    if len(fragment.text) <= 180 and not MAIL.search(fragment.text):
        return fragment
    return None


def _mail_matches(block):
    return [m for m in MAIL.finditer(block.text)
               if not any(mark in block.text[block.text.rfind("\n", 0, m.start()) + 1:m.start()]
                          for mark in ('„', '"', '«'))]


def _read_mail(raw, person):
    value = MAIL_DOTS.sub(".", raw.strip(" ;,.\t"))
    value = OBSCURED_AT.sub("@", value)
    value = re.sub(r"[ \t]*@[ \t]*", "@", value)
    if "@" not in value:
        # At a labelled address Tesseract may read the at sign as q, or as
        # a cluster containing the copyright glyph. A repeated, independently
        # named surname pins the boundary without filling any missing letters.
        surname = person.split()[-1].lower().replace("ł", "l")
        surname = "".join(c for c in unicode_normalize("NFD", surname) if not combining(c))
        if len(surname) >= 4 and re.fullmatch(r"[a-z]+(?:-[a-z]+)?", surname):
            escaped = re.escape(surname)
            boundary = re.fullmatch(
                rf"(?P<local>[a-z0-9._%+-]+\.(?:{escaped}))(?:q|q?©q?)"
                rf"(?P<domain>{escaped}(?:[-.][a-z0-9-]+)+)", value, re.I,
            )
            initial = unicode_normalize("NFD", person[0].lower().replace("ł", "l"))[0]
            if boundary and boundary["local"].split(".", 1)[0].casefold() == initial:
                value = boundary["local"] + "@" + boundary["domain"]
    if MAIL.fullmatch(value):
        local, domain = value.split("@")
        return local + "@" + domain.lower()
    return None


def _mail(block, person):
    matches = _mail_matches(block)
    distinct = {match[0].casefold() for match in matches}
    if len(distinct) == 1:
        return block.group(matches[0]), matches[0][0]
    if len(distinct) > 1:
        labelled = [m for m in matches if DIRECT_MAIL.search(block.text[block.text.rfind("\n", 0, m.start()) + 1:m.start()])]
        if len({match[0].casefold() for match in labelled}) == 1:
            return block.group(labelled[0]), labelled[0][0]
        return None
    labelled = [(block.group(m, "value"), _read_mail(m["value"], person)) for m in MAIL_ROW.finditer(block.text)]
    supported = [(part, value) for part, value in labelled if value]
    return supported[0] if len({value.casefold() for _, value in supported}) == 1 else None


def _counsel(block, marker):
    scope = _trim(block.slice(marker.end())).before(END.pattern)
    profession = PROFESSION.match(scope.text)
    person_scope = scope.slice(profession.end()) if profession else scope
    person = PERSON.match(person_scope.text)
    if not person or NOT_PERSON.search(person["name"]):
        return {}
    person_value = person_scope.group(person, "name")
    remainder = _trim(person_scope.slice(person.end()))
    firm = None
    for row in re.finditer(r"^[ \t]*[^ \t\n\f][^\n\f]*", remainder.text, re.M):
        candidate = remainder.group(row)
        candidate = candidate.slice(re.match(r"(?:adres do korespondencji[ \t]*:[ \t]*|"
                                             r"kancelaria[ \t]*:[ \t]*)?", candidate.text, re.I).end())
        if OFFICE.search(candidate.text) or LEGAL_FORM.search(candidate.text):
            firm = _name(candidate)
            if firm and ":" not in firm.text:
                break
            firm = None
        if candidate.text.startswith(("„", '"', "«")):
            break
    return {"imie_nazwisko": person_value, "nazwa": firm}, _mail(remainder, normalize(person_value.text, "text"))


def _observation(result, section, path, match, rule, value=None):
    literal = normalize(match.text, "text")
    if value is not None and value != literal:
        offset = result.document.starts[0][0] if section.layout else match.offset
        result.put(path, value, offset, rule, source="ocr")
        return
    value = literal
    if not section.layout:
        result.put(path, value, match.offset, rule, span_end=match.offset + len(match.text))
        return
    pattern = r"\s+".join(map(re.escape, match.text.split()))
    occurrences = list(re.finditer(pattern, result.document.text))
    if len(occurrences) == 1:
        start, end = occurrences[0].span()
        result.put(path, value, start, rule, span_end=end, source="ocr")
    else:
        result.put(path, value, result.document.starts[0][0], rule, source="ocr")


def _name_update(previous, candidate, section):
    if not previous or previous == candidate:
        return not previous
    if section.layout:
        return True
    prefix = candidate + " "
    return (previous.startswith(prefix) and bool(ADDRESS.search(previous[len(candidate):]))
            or candidate.startswith(previous + " ") and bool(LEGAL_FORM.search(candidate))
            or previous.lstrip(LEADING_NOISE) == candidate
            or COMPANY_OCR_FORM.sub(r"\1 z o.o.", previous) == candidate
            or (previous.casefold().startswith("konsorcjum ") or TRADE_NAME.search(previous)
                or previous.casefold().startswith("zamawiający wspólnie")) and candidate in previous)


def refine_appeal_parties(result, config, cover):
    """Augment scanned headers without changing the native extraction path."""
    quality = result.document.scan_quality or {}
    ocr = {row["page"] for row in quality.get("pages", ()) if row.get("source") == "ocr"}
    if not ocr or not cover.text:
        return
    sections = []
    if len(result.document.starts) == 1 and 1 in ocr:
        sections = _column_sections(result.document.ocr_layout_tsv)
    if not sections:
        sections = [section for section in _sections(cover)
                    if result.document.page(section.block.offset) in ocr]

    for role in (APPELLANT, BUYER):
        related = [section for section in sections if section.role == role]
        if not related:
            continue
        rows = result.data[role]
        if rows and len(rows) != len(related):
            if not (role == BUYER and len(rows) == 1 and len(related) == 2 and
                    rows[0]["nazwa"] and re.match(r"zamawiaj[ąa]cy\s+wsp[óo]lnie", rows[0]["nazwa"], re.I)
                    and all(section.joint_group for section in related)):
                continue
            rows.clear()
            for field in tuple(result.evidence):
                if field.startswith(BUYER + "."):
                    del result.evidence[field]
        if not rows:
            if any(not _name(section.block) for section in related):
                continue
            rows.extend(empty(config["schema"][role][0]) for _ in related)
        for index, section in enumerate(related):
            _update_party(result, config, index, section)


def _update_party(result, config, index, section):
    path = (section.role, index)
    row = result.data[section.role][index]
    block = section.block
    marker = REPRESENTATION.search(block.text)
    entity = block.slice(0, marker.start()) if marker else block
    name = _name(entity)
    if name:
        value = COMPANY_OCR_FORM.sub(r"\1 z o.o.", normalize(name.text, "text"))
        if _name_update(row["nazwa"], value, section):
            _observation(result, section, (*path, "nazwa"), name, "nazwa_w_naglowku_roli_ocr", value)
    if not section.layout:
        missing = {key: rules for key, rules in config["party_fields"].items() if row[key] is None}
        apply_fields(result, missing, entity.text, entity.offset, path)

    if section.role == BUYER:
        if row["prowadzacy_postepowanie"] is None and len(result.data[BUYER]) > 1 and section.qualifier:
            lead = int(section.qualifier.strip(SEPARATORS).casefold().startswith(("lider", "prowadzący", "prowadzacy")))
            result.put((*path, "prowadzacy_postepowanie"), lead, block.offset, "rola_we_wspolnym_zamowieniu")
        return

    _discard_distribution_contacts(result, path, row, section, marker)
    observed, mail = _counsel(block, marker) if marker else ({}, None)
    if observed:
        if row["przez-pelnomocnika"] != 1:
            result.put((*path, "przez-pelnomocnika"), 1, block.offset, "wykazany_pelnomocnik_odwolujacego")
        for key, match in observed.items():
            if match and (row["pelnomocnik"][key] is None or section.layout or
                          key == "nazwa" and _name_update(row["pelnomocnik"][key],
                                                           normalize(match.text, "text"), section)):
                _observation(result, section, (*path, "pelnomocnik", key), match, "kontakt_przy_umocowaniu_" + key)
        _update_mail(result, path, row, section, marker, mail)
    elif row["przez-pelnomocnika"] is None:
        result.put((*path, "przez-pelnomocnika"), 0, block.offset, "brak_umocowania_w_naglowku")


def _discard_distribution_contacts(result, path, row, section, marker):
    if section.distribution is None:
        return
    own = normalize(section.block.text, "text") or ""
    copied = normalize(section.distribution.text, "text") or ""
    for key, value in row["pelnomocnik"].items():
        if value and value in copied and value not in own:
            row["pelnomocnik"][key] = None
            target = (*path, "pelnomocnik", key)
            result.evidence.pop(".".join(map(str, target)), None)
    if marker is None and row["przez-pelnomocnika"] == 1 and REPRESENTATION.search(section.distribution.text):
        offset = result.document.starts[0][0] if section.layout else section.block.offset
        result.put((*path, "przez-pelnomocnika"), 0, offset, "rozrozniono_odwolujacego_od_odbiorcy_kopii")


def _update_mail(result, path, row, section, marker, mail):
    target = (*path, "pelnomocnik", "mail")
    old = row["pelnomocnik"]["mail"]
    scope = section.block.slice(marker.end())
    valid_old = old and old.casefold() in {m[0].casefold() for m in _mail_matches(scope)}
    if mail and (not valid_old or section.layout):
        part, value = mail
        if part.text == value:
            _observation(result, section, target, part, "mail_przy_umocowaniu_ocr")
        else:
            offset = result.document.starts[0][0] if section.layout else part.offset
            result.put(target, value, offset, "oznaczony_mail_przy_umocowaniu_odczyt_ocr", source="ocr")
    elif old and not valid_old:
        row["pelnomocnik"]["mail"] = None
        result.evidence.pop(".".join(map(str, target)), None)
