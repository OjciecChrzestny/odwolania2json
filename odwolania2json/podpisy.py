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
    r"Załącznik|Podpis osoby|Osoba poświadczająca|Kopia|Poświadczenie)\b|"
    r"\A(?:Pełnomocnictwo\s+przyjmuj|Dokument\s+podpisany)",
    FLAGS,
)
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


def _contains_name(name, line):
    literal = r"\s+".join(map(re.escape, name.split()))
    return re.search(rf"(?<![\w’'-]){literal}(?![\w’'-])", line) is not None


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

    typed_names = {normalize(match["name"], "text") for line in footer for match in ENTRY.finditer(line)}
    if typed_names.difference(names) or not all(any(_contains_name(name, line) for line in footer) for name in names):
        return

    for owner, declared in enumerate(declarations):
        for index, name in enumerate(declared):
            principals[owner]["podpisujacy"].append({})
            # TSV nie mapuje prostokątów na znaki w spłaszczonym tekście.
            result.put(("mocodawca", owner, "podpisujacy", index, "imie_nazwisko"),
                       name, document.offset, SIGNATURE_RULE, source="ocr")
