"""Role w oświadczeniu o udzieleniu pełnomocnictwa."""
from collections import defaultdict
import re

from .model import FLAGS, empty
from .operations import normalize
from .podpisy import NAME, WORD


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


def _ocr_rows(tsv):
    groups = defaultdict(list)
    for row in (tsv or "").splitlines():
        parts = row.split("\t", 11)
        if len(parts) != 12 or parts[0] != "5" or not parts[11].strip():
            continue
        try:
            x, top, width, height = map(int, parts[6:10])
            confidence = float(parts[10])
        except ValueError:
            return {}
        groups[tuple(parts[2:5])].append((x, top, width, height, confidence, parts[11]))
    by_text = defaultdict(list)
    for group in groups.values():
        ordered = sorted(group, key=lambda item: item[0])
        by_text[tuple(item[5] for item in ordered)].append(ordered)
    return by_text


def _detached_margin_glyph(line, observations):
    marker = MARGIN_GLYPH.match(line)
    rows = observations.get(tuple(line.split()), [])
    if not marker or len(rows) != 1:
        return 0
    first, number = rows[0][:2]
    gap = number[0] - (first[0] + first[2])
    return marker.end() if first[4] < 45 and gap >= 3 * max(first[2], number[2]) else 0


LOWER_INITIAL = re.compile(rf"\A(?P<first>[^\W\d_]+)[ \t]+(?P<last>{WORD})\Z")


def _continue_aligned_names(result, config, scope, lines, observations):
    """Zachowaj kolejność prostej listy przy utracie wielkiej litery przez OCR."""
    existing = result.data["pelnomocnicy"]
    if len(existing) < 2 or len(lines) != len(existing) + 1:
        return
    body = [line[0].strip() for line in lines]
    if body[:-1] != [person["imie_nazwisko"] for person in existing]:
        return
    candidate = LOWER_INITIAL.fullmatch(body[-1])
    if not candidate or not candidate["first"].islower():
        return
    selected = [observations.get(tuple(line.split()), []) for line in body]
    if any(len(position) != 1 for position in selected):
        return
    first_words = [position[0][0] for position in selected]
    xs, tops = ([word[i] for word in first_words] for i in (0, 1))
    height = max(word[3] for word in first_words)
    if max(xs) - min(xs) > height or any(not 0 < b - a <= 3 * height for a, b in zip(tops, tops[1:])):
        return
    name = body[-1][0].upper() + body[-1][1:]
    if name in body[:-1]:
        return
    index = len(existing)
    existing.append(empty(config["schema"]["pelnomocnicy"][0]))
    result.put(("pelnomocnicy", index, "imie_nazwisko"), name, scope.offset + lines[-1].start(),
               "osoba_w_kontynuacji_listy_umocowania", source="ocr")


def complete_declared_counsel(result, config, appointment):
    """Odczytaj listę umocowanych bez przestawiania rozpoznanych pozycji."""
    patterns = config["patterns"]
    grant = appointment.find(patterns["grant"])
    if not grant or not grant[0].rstrip().endswith(":"):
        return
    after_grant = appointment.slice(grant.end())
    boundary = after_grant.find(patterns["counsel_end"])
    scope = after_grant.slice(0, boundary.start()) if boundary else after_grant
    scope = scope.slice(0, scope.text.find("\f")) if "\f" in scope.text else scope
    lines = [line for line in re.finditer(r"[^\n]+", scope.text) if line[0].strip()]
    observations = _ocr_rows(result.document.ocr_layout_tsv)
    if result.data["pelnomocnicy"]:
        if boundary and re.match(r"do\s+(?:reprezentowania|reprezentacji)\b", boundary[0], FLAGS):
            _continue_aligned_names(result, config, scope, lines, observations)
        return
    entries = []
    for line in lines:
        line_span = scope.slice(line.start(), line.end())
        match = NUMBERED_COUNSEL.fullmatch(line_span.text)
        if not match:
            margin = _detached_margin_glyph(line_span.text, observations)
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
