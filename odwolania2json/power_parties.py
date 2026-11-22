"""Role w oświadczeniu o udzieleniu pełnomocnictwa."""
from collections import defaultdict
import re

from .model import FLAGS, empty
from .operations import normalize
from .podpisy import NAME


NUMBERED_COUNSEL = re.compile(
    rf"^[ \t]*(?P<index>[1-9]\d*)[.)][ \t]+(?P<name>{NAME})[ \t]*[–—-][ \t]*"
    r"(?:adwokat|radca[ \t]+prawny|r\.[ \t]*pr\.)"
    r"(?P<details>[ \t]*(?:,[ \t]*(?:(?:nr\b|PESEL\b)[^\n\f]*)?)?)[ \t]*$",
    FLAGS,
)
SELF_DECLARATION = re.compile(
    rf"\A[ \t]*Ja,[ \t]*(?:niżej[ \t]+)?podpisan(?:y(?:/a)?|a)[ \t]+(?P<name>{NAME})[ \t]*,",
    FLAGS,
)
SOLO_BUSINESS = re.compile(
    r"\bprowadz(?:ący(?:/a|/ąca)?|ąca|ę)[ \t\n]+działalność[ \t\n]+gospodarczą\b",
    FLAGS,
)


def _put_span(result, path, fragment, match, group, rule, operation="text"):
    start, end = match.span(group)
    value = normalize(match[group], operation)
    result.put(path, value, fragment.offset + start, rule, span_end=fragment.offset + end,
               operation=operation)


def refine_declared_grantor(result, blocks):
    """Rozpoznaj osobę fizyczną z jednoznacznego oświadczenia własnego."""
    principals = result.data["mocodawca"]
    if len(principals) != 1 or len(blocks) != 1:
        return
    data = principals[0]["data"]
    if data["typ"] != "osoba_prawna" or data["krs"] or data["imie_nazwisko"]:
        return
    block = blocks[0].stripped()
    opening = SELF_DECLARATION.match(block.text)
    if not opening or not SOLO_BUSINESS.match(block.text[opening.end():].lstrip()):
        return

    prefix = ("mocodawca", 0, "data")
    data["nazwa"] = None
    result.evidence.pop("mocodawca.0.data.nazwa", None)
    _put_span(result, (*prefix, "imie_nazwisko"), block, opening, "name", "osoba_w_oswiadczeniu_mocodawcy")
    result.put((*prefix, "typ"), "osoba_fizyczna", block.offset + opening.start("name"),
               "osoba_fizyczna_w_oswiadczeniu")



COMPANY_FORM = re.compile(r"(?P<form>\bsp\.[ \t]+z[ \t]+)(?P<suffix>[o0]\.[o0]\.?)\Z", FLAGS)


def refine_company_form(result, blocks):
    """Przywróć litery o w zamkniętym skrócie formy prawnej odczytanym z OCR."""
    principals = result.data["mocodawca"]
    if not result.document.ocr_layout_tsv or len(principals) != len(blocks):
        return
    for index, (principal, block) in enumerate(zip(principals, blocks)):
        data = principal["data"]
        name = data["nazwa"]
        suffix = COMPANY_FORM.search(name or "")
        if data["typ"] != "osoba_prawna" or not suffix or "0" not in suffix["suffix"]:
            continue
        corrected = name[:suffix.start("suffix")] + suffix["suffix"].replace("0", "o")
        result.put(("mocodawca", index, "data", "nazwa"), corrected, block.offset,
                   "skrot_formy_prawnej_mocodawcy_z_ocr", source="ocr")


MARGIN_GLYPH = re.compile(r"\A[ \t]*[^\W\d_][ \t]+(?=[1-9]\d*[.)][ \t])")


def _detached_margin_glyph(line, tsv):
    marker = MARGIN_GLYPH.match(line)
    if not marker or not tsv:
        return 0
    words = tuple(line.split())
    groups = defaultdict(list)
    for row in tsv.splitlines():
        parts = row.split("\t", 11)
        if len(parts) == 12 and parts[0] == "5" and parts[11].strip():
            try:
                x, width, confidence = int(parts[6]), int(parts[8]), float(parts[10])
            except ValueError:
                return 0
            groups[tuple(parts[2:5])].append((x, width, confidence, parts[11]))
    for group in groups.values():
        ordered = sorted(group)
        if tuple(item[3] for item in ordered) != words:
            continue
        first, number = ordered[:2]
        gap = number[0] - (first[0] + first[1])
        if first[2] < 45 and gap >= 3 * max(first[1], number[1]):
            return marker.end()
    return 0


def add_numbered_counsel(result, config, appointment):
    """Uzupełnij pustą listę z numerowanych wierszy po formule udzielenia."""
    if result.data["pelnomocnicy"]:
        return
    patterns = config["patterns"]
    grant = appointment.find(patterns["grant"])
    if not grant or not grant[0].rstrip().endswith(":"):
        return
    scope = appointment.slice(grant.end()).before(patterns["counsel_end"])
    scope = scope.slice(0, scope.text.find("\f")) if "\f" in scope.text else scope
    entries = []
    for line in re.finditer(r"[^\n]+", scope.text):
        if not line[0].strip():
            continue
        line_span = scope.slice(line.start(), line.end())
        match = NUMBERED_COUNSEL.fullmatch(line_span.text)
        if not match:
            margin = _detached_margin_glyph(line_span.text, result.document.ocr_layout_tsv)
            line_span = line_span.slice(margin)
            match = NUMBERED_COUNSEL.fullmatch(line_span.text)
        if not match or int(match["index"]) != len(entries) + 1:
            return
        entries.append((line_span, match))

    for index, (line, match) in enumerate(entries):
        result.data["pelnomocnicy"].append(empty(config["schema"]["pelnomocnicy"][0]))
        path = ("pelnomocnicy", index)
        _put_span(result, (*path, "imie_nazwisko"), line, match, "name",
                  "osoba_w_numerowanej_liscie_umocowania")
        details = line.group(match, "details")
        for rule in config["counsel_fields"]["pesel"]:
            if pesel := details.find(rule["pattern"]):
                _put_span(result, (*path, "pesel"), details, pesel, 1, rule["name"], rule["operation"])
                break
