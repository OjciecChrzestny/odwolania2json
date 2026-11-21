"""Opcjonalny OCR uruchamiany lokalnie dla stron bez warstwy tekstowej."""
import re
from contextlib import closing
from functools import partial


def prepare_ocr(data):
    try:
        from pypdfium2 import PdfDocument
        from tesserocr import PyTessBaseAPI
    except ImportError as exc:
        raise ValueError("OCR wymaga instalacji requirements-ocr.txt") from exc
    if not (data / "pol.traineddata").is_file():
        raise ValueError(f"Brak pol.traineddata w {data}")
    return partial(recognize, PdfDocument, PyTessBaseAPI, data)


_REFERENCE_LINE = re.compile(
    r"^[ \t]*(?:nr ref\.?|numer referencyjny|transaction reference)[.: \t]+"
    r"(?P<value>[a-zA-Z0-9][a-zA-Z0-9_./-]{2,39})[ \t]*$", re.I | re.M,
)


def refine_bank_reference(text, api, bitmap, api_type, data):
    """Retry a low-confidence ID in its own box; retain the digits observed on the page."""
    if not re.search(r"\b(?:przelew\w*|potwierdzenie wykonania operacji|transfer confirmation)\b", text, re.I):
        return text
    match = _REFERENCE_LINE.search(text)
    if not match:
        return text
    original = match["value"]
    digits = re.sub(r"\D", "", original)
    if not digits:
        return text
    words = [row.split("\t", 11) for row in api.GetTSVText(0).splitlines()]
    tokens = [w for w in words if len(w) == 12 and w[0] == "5" and w[-1] == original]
    if len(tokens) != 1 or float(tokens[0][10]) > 50:
        return text
    x, y, width, height = map(int, tokens[0][6:10])
    readings = []
    with api_type(path=str(data), lang="pol", psm=7) as line_api:  # Tesseract SINGLE_LINE
        line_api.SetVariable("tessedit_char_whitelist", "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz/._-")
        line_api.SetImageBytes(bytes(bitmap.buffer), bitmap.width, bitmap.height, bitmap.n_channels, bitmap.stride)
        for xpad, ypad in ((4, 3), (8, 5)):
            left, top = max(0, x - xpad), max(0, y - ypad)
            right, bottom = min(bitmap.width, x + width + xpad + 2), min(bitmap.height, y + height + ypad)
            line_api.SetRectangle(left, top, right - left, bottom - top)
            value = line_api.GetUTF8Text().strip()
            if line_api.MeanTextConf() < 60 or re.sub(r"\D", "", value) != digits:
                return text
            readings.append(value)
    value = readings[0]
    if value != readings[1] or original not in value or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./-]{2,39}", value):
        return text
    return text[:match.start("value")] + value + text[match.end("value"):]


def recognize(document_type, api_type, data, path, limit, *, start=0):
    with closing(document_type(path)) as pdf, api_type(path=str(data), lang="pol") as api:
        api.SetVariable("user_defined_dpi", "180")
        for index in range(start, limit):
            with closing(pdf[index]) as page:
                scale = min(2.5, 2200 / max(page.get_size()))
                best = ""
                for angle in (0, 90, 270, 180):
                    with closing(page.render(scale=scale, rotation=angle, grayscale=True)) as bitmap:
                        api.SetImageBytes(bytes(bitmap.buffer), bitmap.width, bitmap.height,
                                          bitmap.n_channels, bitmap.stride)
                        text = api.GetUTF8Text()
                        if len(text) > len(best):
                            best = text
                        if len(text.split()) >= 8 and api.MeanTextConf() >= 55:
                            if text == best:
                                best = refine_bank_reference(text, api, bitmap, api_type, data)
                            break
                yield index, best
