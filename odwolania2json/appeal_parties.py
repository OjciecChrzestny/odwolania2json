"""Ground appeal parties and their procedural representative in scanned headers."""
from dataclasses import dataclass
import re
from statistics import median

from .bank_scan import word_rows
from .legal import Fragment
from .model import FLAGS, empty
from .operations import apply_fields, normalize

APPELLANT, BUYER = "Odwolujacy", "Zamawiajacy"
ROLE = re.compile(
    r"(?:^[ \t]*(?:\d{1,2}[.)][ \t]*)?|(?<=[ \t|])(?=(?:odwo[łl]uj|zamawiaj)))"
    r"(?P<role>odwo[łl]uj[ąa]c[yae]|zamawiaj[ąa]c[yae])"
    r"(?P<qualifier>[ \t]*[–—-][ \t]*(?:lider|prowadz[ąa]cy|partner)\b[^:\n\f]{0,38})?"
    r"[ \t]*(?:[:：][ \t]*|[–—][ \t]+|(?=$))", FLAGS,
)
END = re.compile(
    r"^[ \t]*(?:ODWO[ŁL]ANIE[ \t]*:?$|Dotyczy\b|Wnosz[ęe] (?:o |odwo[łl]anie)|"
    r"Zarzuty\b|Uzasadnienie\b|Przedmiot zam[óo]wienia\b|Za[łl][ąa]czniki\b|"
    r"Do wiadomo[śs]ci\b|Stopka\b|Podpis\b|Cytat\b)", FLAGS,
)
REPRESENTATION = re.compile(
    r"\b(?:reprezentowan[yaeią][\s]+przez|dzia[łl]aj[ąa]c[yae][\s]+przez|"
    r"zast[ęe]powan[yaeią][\s]+przez|pe[łl]nomocnik(?:[ \t]+(?:procesowy|odwo[łl]uj[ąa]cego|"
    r"wykonawcy))?(?=[ \t]*[:：]|[ \t\n]+(?:adw|radc|r[. ])))"
    r"[ \t\n]*[:：]?[ \t\n]*", FLAGS,
)
PROFESSION = re.compile(
    r"^(?:adw(?:okat\w*)?\.?|radc(?:a|ę|y)[ \t]+prawn(?:y|ego)|r\.?[ \t]*p(?:r)?\.)[ \t\n]+",
    re.I,
)
ADDRESS = re.compile(
    r"(?:^|[ \t,;])(?:ul(?:ica)?\.?[ \t]+|al\.?[ \t]+|pl\.[ \t]+|"
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
PERSON = re.compile(
    r"(?P<name>[A-ZĄĆĘŁŃÓŚŹŻ][^\W\d_]+(?:[-’'][A-ZĄĆĘŁŃÓŚŹŻ][^\W\d_]+)?"
    r"[ \t\n]+[A-ZĄĆĘŁŃÓŚŹŻ][^\W\d_]+(?:[-’'][A-ZĄĆĘŁŃÓŚŹŻ][^\W\d_]+)?)"
)
NOT_PERSON = re.compile(r"\b(?:kancelaria|radca|adwokat|ulica|pełnomocnik|kontakt|adres|nr)\b", re.I)
SEPARATORS = " \t\n,;:|–—"


@dataclass(frozen=True)
class Section:
    role: str
    qualifier: str
    block: Fragment
    layout: bool = False


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
        block = header.slice(label.end(), end).before(END.pattern)
        yield Section(_role(label["role"]), label["qualifier"] or "", block)


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
            if END.match(line):
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
            sections.append(Section(item.role, item.qualifier, item.block, layout=True))
        if len(sections) == 2 and all(_name(item.block) for item in sections):
            return sections
    return []


def _trim(block):
    start = len(block.text) - len(block.text.lstrip(SEPARATORS))
    stop = len(block.text.rstrip(SEPARATORS))
    return block.slice(start, max(start, stop))


def _name(block):
    block = _trim(block)
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


def _mail(block):
    matches = _mail_matches(block)
    distinct = {match[0].casefold() for match in matches}
    if len(distinct) > 1:
        labelled = [m for m in matches if DIRECT_MAIL.search(block.text[block.text.rfind("\n", 0, m.start()) + 1:m.start()])]
        matches = labelled if len({match[0].casefold() for match in labelled}) == 1 else []
    return block.group(matches[0]) if matches else None


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
            if firm:
                break
        if candidate.text.startswith(("„", '"', "«")):
            break
    return {"imie_nazwisko": person_value, "nazwa": firm, "mail": _mail(remainder)}


def _observation(result, section, path, match, rule):
    value = normalize(match.text, "text")
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
            or candidate.startswith(previous + " ") and bool(LEGAL_FORM.search(candidate)))


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
            continue
        for section in related:
            if not rows and not _name(section.block):
                break
        else:
            if not rows:
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
    if name and _name_update(row["nazwa"], normalize(name.text, "text"), section):
        _observation(result, section, (*path, "nazwa"), name, "nazwa_w_naglowku_roli_ocr")
    if not section.layout:
        missing = {key: rules for key, rules in config["party_fields"].items() if row[key] is None}
        apply_fields(result, missing, entity.text, entity.offset, path)

    if section.role == BUYER:
        if row["prowadzacy_postepowanie"] is None and len(result.data[BUYER]) > 1 and section.qualifier:
            lead = int(section.qualifier.strip(SEPARATORS).casefold().startswith(("lider", "prowadzący", "prowadzacy")))
            result.put((*path, "prowadzacy_postepowanie"), lead, block.offset, "rola_we_wspolnym_zamowieniu")
        return

    observed = _counsel(block, marker) if marker else {}
    if observed:
        if row["przez-pelnomocnika"] != 1:
            result.put((*path, "przez-pelnomocnika"), 1, block.offset, "wykazany_pelnomocnik_odwolujacego")
        for key, match in observed.items():
            target = (*path, "pelnomocnik", key)
            old = row["pelnomocnik"][key]
            invalid = key == "mail" and old and old.casefold() not in {
                occurrence[0].casefold() for occurrence in _mail_matches(block.slice(marker.end()))
            }
            if match and (old is None or section.layout or invalid):
                _observation(result, section, target, match, "kontakt_przy_umocowaniu_" + key)
            elif invalid:
                row["pelnomocnik"][key] = None
                result.evidence.pop(".".join(map(str, target)), None)
    elif row["przez-pelnomocnika"] is None:
        result.put((*path, "przez-pelnomocnika"), 0, block.offset, "brak_umocowania_w_naglowku")
