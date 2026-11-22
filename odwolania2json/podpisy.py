"""Powiązanie podpisów z deklaracją reprezentacji i stopką mocodawcy."""
from collections import defaultdict
import re

from .model import FLAGS
from .operations import normalize


WORD = r"(?-i:[A-ZĄĆĘŁŃÓŚŹŻ][^\W\d_]+(?:[-’'][A-ZĄĆĘŁŃÓŚŹŻ][^\W\d_]+)?)"
NAME = rf"{WORD}(?:\s+{WORD}){{1,3}}"
OFFICE = r"(?:Prezes|Wiceprezes|Członek)\s+Zarządu|Prokurent"
ENTRY = re.compile(rf"(?P<name>{NAME})\s*[–—-]\s*(?:{OFFICE})\b", FLAGS)
REPRESENTATION = re.compile(r"\breprezentowan(?:a|y|e|ą|i)[\s_]+przez\s*:", FLAGS)
PRINCIPAL_SIGNATURES = re.compile(r"\AZa\s+Mocodawcę\s*:?\s*\Z", FLAGS)
NEXT_SECTION = re.compile(
    r"\A(?:NIP|KRS|REGON|Data|Świadek|Świadkowie|Pełnomocnik|Sprawdzenie|W imieniu|"
    r"Załącznik|Podpis osoby|Osoba poświadczająca|Kopia|Poświadczenie|Wykaz|Lista|"
    r"Osoby|Uprawnieni|Upoważnieni|Odbiór|Odbiorca|Odebrano|Potwierdzenie|Doręczenie|"
    r"Potwierdzili|Potwierdził|Potwierdziła|Przekazanie)\b|"
    r"\A(?:Pełnomocnictwo\s+przyjmuj|Dokument\s+podpisany|Podpis\s+odbiorcy)",
    FLAGS,
)
NO_SIGNATURE = re.compile(
    r"\b(?:nie\s+podpisano|nie\s+został[oa]?\s+podpisan[yae]|niepodpisan[yae]|"
    r"(?:brak|bez|nie\s+ma|brakuje)\s+(?:(?:obu|wszystkich|wymagan\w+)\s+)?podpis(?:u|ów)|"
    r"nie\s+złożono\s+(?:żadnego\s+)?podpis(?:u|ów)|podpis(?:u|ów)\s+nie\s+złożono)\b",
    FLAGS,
)
ROW_GAP = re.compile(r"[\s.,;:=_–—-]*")
WORD_FRAGMENT = re.compile(r"[^\W\d_]+")
GRAPHIC_MARK = re.compile(r"[\d_/|<>=–—-]")
SIGNATURE_RULE = "podpis_za_mocodawce_i_deklaracja_reprezentacji"


def _layout_lines(tsv):
    lines = defaultdict(list)
    for raw in tsv.splitlines():
        columns = raw.split("\t", 11)
        if len(columns) != 12 or columns[0] != "5" or not columns[11].strip():
            continue
        try:
            left, top = map(int, columns[6:8])
        except ValueError:
            return []
        lines[tuple(columns[2:5])].append((left, top, columns[11]))

    positioned = []
    for tokens in lines.values():
        left = min(token[0] for token in tokens)
        top = min(token[1] for token in tokens)
        text = " ".join(token[2] for token in sorted(tokens))
        positioned.append((top, left, text))
    return [text for _, _, text in sorted(positioned, key=lambda line: (line[0], line[1]))]


def _representatives(text):
    label = REPRESENTATION.search(text)
    if not label:
        return []
    return [normalize(match["name"], "text") for match in ENTRY.finditer(text, label.end())]


def _signature_row(line, entry):
    matches = list(entry.finditer(line))
    if not matches:
        return []
    cursor = 0
    for match in matches:
        if not ROW_GAP.fullmatch(line[cursor:match.start()]):
            return []
        cursor = match.end()
    if not ROW_GAP.fullmatch(line[cursor:]):
        return []
    if len(matches) > 1 and any(not match["office"] for match in matches):
        return []
    return matches


def _is_graphic_fragment(line):
    # Tesseract może sczytać kreski i kilka izolowanych znaków z odręcznej parafy.
    words = WORD_FRAGMENT.findall(line)
    return not words or (
        len(words) <= 2 and all(len(word) <= 4 for word in words) and GRAPHIC_MARK.search(line) is not None
    )


def _confirmed_footer_names(footer, names):
    if NO_SIGNATURE.search("\n".join(footer)):
        return set()
    alternatives = "|".join(r"\s+".join(map(re.escape, name.split())) for name in sorted(names, key=len, reverse=True))
    entry = re.compile(rf"(?<![\w’'-])(?P<name>{alternatives})(?![\w’'-])"
                       rf"(?:\s*[–—-]\s*(?P<office>(?i:{OFFICE})))?")
    confirmed = set()
    has_office = False
    for line in footer:
        matches = _signature_row(line, entry)
        if not matches:
            if ENTRY.search(line):
                return set()
            if _is_graphic_fragment(line):
                continue
            break
        for match in matches:
            name = normalize(match["name"], "text")
            if name in confirmed:
                return set()
            confirmed.add(name)
            has_office = has_office or bool(match["office"])
    return confirmed if has_office else set()


def add_confirmed_signatures(result, config, document, blocks, layout_tsv):
    """Uzupełnij puste listy na podstawie odczytu i układu tej samej strony OCR."""
    if not layout_tsv or len(result.document.starts) != 1:
        return
    principals = result.data["mocodawca"]
    if not principals or any(row["podpisujacy"] or row["data"]["typ"] != "osoba_prawna" for row in principals):
        return

    patterns = config["patterns"]
    signing = document.before(patterns["acceptance"])
    grant = signing.find(patterns["grant"])
    if not grant or not any(PRINCIPAL_SIGNATURES.fullmatch(line.strip())
                            for line in signing.text[grant.end():].splitlines()):
        return
    starts = [block.offset - signing.offset for block in blocks]
    if len(starts) != len(principals) or starts != sorted(set(starts)) or starts[-1] >= grant.start():
        return
    declarations = [_representatives(signing.text[start:end])
                    for start, end in zip(starts, [*starts[1:], grant.start()])]
    names = [name for group in declarations for name in group]
    if any(not group for group in declarations) or len(set(names)) != len(names):
        return

    layout = _layout_lines(layout_tsv)
    anchors = [index for index, line in enumerate(layout) if PRINCIPAL_SIGNATURES.fullmatch(line.strip())]
    if len(anchors) != 1:
        return
    footer = []
    for line in layout[anchors[0] + 1:]:
        if NEXT_SECTION.search(line):
            break
        footer.append(line)

    if _confirmed_footer_names(footer, names) != set(names):
        return

    for owner, declared in enumerate(declarations):
        for index, name in enumerate(declared):
            principals[owner]["podpisujacy"].append({})
            # TSV nie mapuje prostokątów na znaki w spłaszczonym tekście.
            result.put(("mocodawca", owner, "podpisujacy", index, "imie_nazwisko"),
                       name, document.offset, SIGNATURE_RULE, source="ocr")


ELECTRONIC_SIGNATURE = re.compile(
    rf"^[ \t]*Dokument[ \t]+podpis?any[ \t]+przez[ \t]*:?[ \t]*(?P<name>{NAME})[ \t]*$",
    FLAGS,
)
ELECTRONIC_TIME = re.compile(r"\AData(?:[ \t]+podpisu)?[ \t]*:[ \t]*[^\n]*\d{1,2}:\d{2}\b", FLAGS)
OTHER_CERTIFICATE_ROLE = re.compile(
    r"^[ \t]*(?:Świad(?:ek|kowie)|Adresat|Odbiorca|Odbiór|Potwierdzenie|Poświadczenie|"
    r"Podpis[ \t]+pełnomocnika|Kopia|Pouczenie|Cytat|Przyjęcie[ \t]+pełnomocnictwa)\b",
    FLAGS,
)


def add_electronic_signature(result, config, document, blocks):
    """Połącz oznaczone potwierdzenie podpisu z jedynym zadeklarowanym reprezentantem."""
    source = result.document
    principals = result.data["mocodawca"]
    if not source.ocr_layout_tsv or len(source.starts) != 1 or len(principals) != 1 or len(blocks) != 1:
        return
    principal = principals[0]
    if principal["podpisujacy"]:
        return

    signing = document.before(config["patterns"]["acceptance"])
    grant = signing.find(config["patterns"]["grant"])
    if not grant:
        return
    footer = signing.slice(grant.end())
    certificates = list(ELECTRONIC_SIGNATURE.finditer(footer.text))
    if len(certificates) != 1 or NO_SIGNATURE.search(footer.text):
        return
    certificate = certificates[0]
    if OTHER_CERTIFICATE_ROLE.search(footer.text[:certificate.start()]):
        return

    layout = _layout_lines(source.ocr_layout_tsv)
    evidence = [(value, layout[index + 1]) for index, line in enumerate(layout[:-1])
                if (value := ELECTRONIC_SIGNATURE.fullmatch(line))]
    name = normalize(certificate["name"], "text")
    if len(evidence) != 1 or normalize(evidence[0][0]["name"], "text") != name or not ELECTRONIC_TIME.match(evidence[0][1]):
        return

    data = principal["data"]
    if data["typ"] == "osoba_fizyczna":
        declared = [data["imie_nazwisko"]]
    else:
        start = blocks[0].offset - signing.offset
        declared = _representatives(signing.text[start:grant.start()])
    if declared != [name]:
        return

    principal["podpisujacy"].append({})
    start, end = certificate.span("name")
    result.put(("mocodawca", 0, "podpisujacy", 0, "imie_nazwisko"),
               name, footer.offset + start, "podpis_elektroniczny_osoby_z_deklaracji",
               span_end=footer.offset + end, source="ocr")
