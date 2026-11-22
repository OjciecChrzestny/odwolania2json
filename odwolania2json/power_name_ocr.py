"""Optional, field-only confirmation of a corporate principal's OCR name."""
from contextlib import closing
from dataclasses import dataclass
from functools import cache
from pathlib import Path
import re
from statistics import mean, median
import unicodedata

from .extract import PAGE_READ_ERRORS, clean_page
from .legal import Fragment, principal_blocks
from .model import DEFAULT_CONFIG, FLAGS, Document, load_classes
from .ocr import LocalOCR
from .power_parties import current_appointment


RULE = "nazwa_mocodawcy_z_odczytu_strony_i_wycinka"
IDENTIFIER = re.compile(
    r"\b(?P<kind>KRS|NIP)[ \t]*(?:[:.][ \t]*)?"
    r"(?P<digits>[0-9](?:[ \t-]*[0-9]){9})(?![ \t-]*[0-9])",
    FLAGS,
)
OTHER_ROLE = re.compile(
    r"^[ \t]*(?:pełnomocni(?:k|cy)|odbiorca|adresat|zamawiający|beneficjent|kancelaria)"
    r"[ \t]*(?::|[ \t]+jest\b|$)",
    FLAGS,
)
MODEL_OR_CITATION = re.compile(
    r"^[ \t]*(?:wzór|przykład|instrukcja|cytat|przytoczenie)(?:[ \t:]+|$)", FLAGS,
)
COMPOSITE_NAME = re.compile(
    r"(?:\bsp\.[ \t]*z[ \t]*o\.[ \t]*o\.|\bs\.a\.|"
    r"\bspółka[ \t]+(?:akcyjna|z[ \t]+ograniczoną[ \t]+odpowiedzialnością))"
    r"(?:[ \t]*[,;+][ \t]*|\s+(?:i|oraz)\s+)\S",
    FLAGS,
)
DPI = 300
MAX_EDGE = 3700


@dataclass(frozen=True)
class Declaration:
    name: str
    context: str
    heading: str


@dataclass(frozen=True)
class Word:
    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float


@cache
def _patterns():
    return load_classes(DEFAULT_CONFIG)["pelnomocnictwo"]


def _literal(text):
    return " ".join(unicodedata.normalize("NFC", text).strip(" ,;:\t\r\n").split())


def _same_role_declaration(text, identity):
    config = _patterns()
    patterns = config["patterns"]
    text = clean_page(text)
    if "\f" in text:
        return None
    headings = list(re.finditer(patterns["header"], text, FLAGS))
    if len(headings) != 1 or headings[0].start() > 1200:
        return None
    heading = headings[0]
    grant = re.compile(patterns["grant"], FLAGS).search(text, heading.end())
    if not grant or grant.start() - heading.end() > 1800:
        return None
    opening = text[:grant.start()]
    if OTHER_ROLE.search(opening) or MODEL_OR_CITATION.search(opening):
        return None
    active = current_appointment(Document.from_pages([text])).text
    if active[heading.start():heading.end()] != heading[0] or active[grant.start():grant.end()] != grant[0]:
        return None

    blocks = principal_blocks(Fragment(text[heading.start():], heading.start()), config)
    if len(blocks) != 1:
        return None
    block = blocks[0].stripped()
    if not heading.end() <= block.offset < grant.start() or block.offset + len(block.text) > grant.start():
        return None
    matches = list(IDENTIFIER.finditer(opening))
    if len(matches) != len(identity):
        return None
    observed = {}
    for match in matches:
        if not block.offset <= match.start() < match.end() <= block.offset + len(block.text):
            return None
        if active[match.start():match.end()] != match[0]:
            return None
        label = match["kind"].lower()
        observed[label] = re.sub(r"\D", "", match["digits"])
    if observed != identity:
        return None
    region = block.before(patterns["name_end"]).stripped()
    # Some declarations put the labelled number directly after the name.
    region = region.before(IDENTIFIER.pattern).stripped()
    name = _literal(region.text)
    if not (3 <= len(name) <= 120 and any(c.isalpha() for c in name)
            and region.text.count("\n") <= 2 and region.offset + len(region.text) <= matches[0].start()):
        return None
    if COMPOSITE_NAME.search(name):
        return None
    end = matches[-1].end()
    if end - region.offset > 420:
        return None
    return Declaration(name, text[region.offset:end], heading[0].strip())


def _words(tsv):
    parsed = []
    for line in tsv.splitlines():
        columns = line.split("\t", 11)
        if len(columns) == 12 and columns[0] == "5" and columns[-1].strip():
            parsed.append(Word(columns[-1], *map(int, columns[6:10]), float(columns[10])))
    return parsed


def _unique_name_box(tsv, name, width, height):
    words = _words(tsv)
    length = len(name.split())
    matches = [words[i:i + length] for i in range(len(words) - length + 1)
               if _literal(" ".join(word.text for word in words[i:i + length])) == name]
    if len(matches) != 1:
        return None
    selected = matches[0]
    if min(word.confidence for word in selected) < 25 or mean(word.confidence for word in selected) < 75:
        return None
    pad = max(3, round(median(word.height for word in selected) * .18))
    left = max(0, min(word.left for word in selected) - pad)
    top = max(0, min(word.top for word in selected) - pad)
    right = min(width, max(word.left + word.width for word in selected) + pad)
    bottom = min(height, max(word.top + word.height for word in selected) + pad)
    if right <= left or bottom <= top:
        return None
    return left, top, right - left, bottom - top


def _set_image(api, bitmap, pixels, dpi):
    api.SetVariable("user_defined_dpi", str(dpi))
    api.SetImageBytes(pixels, bitmap.width, bitmap.height, bitmap.n_channels, bitmap.stride)


def _read_name(pdf, ocr, page_number, identity, original):
    with closing(ocr.document_type(pdf)) as source, closing(source[page_number - 1]) as page:
        scale = min(DPI / 72, MAX_EDGE / max(page.get_size()))
        dpi = round(scale * 72)
        with closing(page.render(scale=scale, grayscale=True)) as bitmap:
            pixels = bytes(bitmap.buffer)
            with ocr.api_type(path=str(ocr.data), lang="pol", psm=3) as reader:
                _set_image(reader, bitmap, pixels, dpi)
                declaration = _same_role_declaration(reader.GetUTF8Text(), identity)
                if declaration is None or declaration.name == original:
                    return None
                rectangle = _unique_name_box(reader.GetTSVText(0), declaration.name,
                                             bitmap.width, bitmap.height)
            if rectangle is None:
                return None
            # An independent segmentation reads only the physical name crop.
            with ocr.api_type(path=str(ocr.data), lang="pol", psm=6) as confirm:
                _set_image(confirm, bitmap, pixels, dpi)
                confirm.SetRectangle(*rectangle)
                if (_literal(confirm.GetUTF8Text()) != declaration.name
                        or confirm.MeanTextConf() < 75):
                    return None
    x, y, width, height = rectangle
    evidence = {"page": page_number, "source": "ocr", "rule": RULE, "precision": "snippet",
                "snippet": declaration.name, "context": declaration.context,
                "page_heading": declaration.heading,
                "ocr_box": {"x": x, "y": y, "width": width, "height": height,
                            "units": "pixel", "origin": "top_left", "rotation": 0,
                            "dpi": dpi, "confirmed_psm": 6}}
    return declaration.name, evidence


def _identity(data):
    nip, krs = data.get("nip"), data.get("krs")
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9]{10}", value) for value in (nip, krs)):
        return None
    digits = list(map(int, nip))
    if sum(a * b for a, b in zip(digits, (6, 5, 7, 2, 3, 4, 5, 6, 7))) % 11 != digits[-1]:
        return None
    return {"krs": krs, "nip": nip}


def verify_power_name(pdf: Path, ocr, value, record, ocr_pages):
    """Return the extraction with at most mocodawca.0.data.nazwa replaced."""
    if (not isinstance(ocr, LocalOCR) or value is None or record.get("class") != "pelnomocnictwo"
            or record.get("status") != "ok" or not ocr_pages):
        return value, record
    principals = value["mocodawca"]
    if len(principals) != 1 or principals[0]["data"]["typ"] != "osoba_prawna":
        return value, record
    data = principals[0]["data"]
    identifiers = _identity(data)
    if identifiers is None:
        return value, record
    prefix = "mocodawca.0.data."
    fields = record["fields"]
    original = data["nazwa"]
    keys = ("krs", "nip", "nazwa") if original else ("krs", "nip")
    observed = [fields.get(prefix + key, {}) for key in keys]
    page = observed[0].get("page")
    if (type(page) is not int or page < 1 or page not in ocr_pages or
            any(item.get("page") != page or item.get("source") not in {None, "ocr"} for item in observed)):
        return value, record
    try:
        confirmed = _read_name(pdf, ocr, page, identifiers, original)
    except PAGE_READ_ERRORS:
        return value, record
    if confirmed is None:
        return value, record
    name, evidence = confirmed
    updated = {**principals[0], "data": {**data, "nazwa": name}}
    return {**value, "mocodawca": [updated]}, {**record, "fields": {**fields, prefix + "nazwa": evidence}}
