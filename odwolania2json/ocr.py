"""Opcjonalny OCR uruchamiany lokalnie dla stron bez warstwy tekstowej."""
import logging
import re
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from functools import partial
from itertools import islice
from math import ceil
from pathlib import Path

from .bank_accounts import account_layout, valid_nrb
from .bank_scan import ScanView, Word, numeric_boxes, recovered_numbers, token_value, row_text, word_rows


def prepare_ocr(data):
    try:
        from pypdfium2 import PdfDocument
        from tesserocr import PyTessBaseAPI
    except ImportError as exc:
        raise ValueError("OCR wymaga instalacji requirements-ocr.txt") from exc
    if not (data / "pol.traineddata").is_file():
        raise ValueError(f"Brak pol.traineddata w {data}")
    # tesserocr defaults to /dev/null. Tesseract 5.5.4 can dereference a null
    # stream if the sandbox denies opening it for writing. Use the open stderr.
    api_type = partial(PyTessBaseAPI, variables={"debug_file": ""})
    return LocalOCR(PdfDocument, api_type, data)


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


def account_crops(positions):
    """Retry nearly complete numeric groups in their own box, within one visual row."""
    for row_index, _, _, divider in account_layout(row_text(positions), positions):
        row = positions[row_index]
        boundary = ceil(divider) if divider is not None else None
        if boundary is not None and any(w.x < boundary < w.x + w.width for w in row):
            # A bounding box that crosses the divider makes this row ambiguous.
            continue
        start = 0
        while start < len(row):
            word = row[start]
            if not re.fullmatch(r"(?:PL)?[0-9IOol|()/]+", word.text):
                start += 1
                continue
            x_min, x_max = 0, None
            if boundary is not None:
                if word.x < boundary:
                    x_max = boundary
                else:
                    x_min = boundary
            end = start + 1
            while end < len(row):
                following, previous = row[end], row[end - 1]
                gap = following.x - (previous.x + previous.width)
                if (x_max is not None and following.x >= x_max
                        or gap > 2 * max(previous.height, following.height)
                        or not re.fullmatch(r"[0-9IOol|()/]+", following.text)):
                    break
                end += 1
            chunk = row[start:end]
            text = "".join(w.text for w in chunk).removeprefix("PL")
            digits = re.sub(r"[^0-9]", "", text)
            if 23 <= len(digits) <= 27 and 24 <= len(text) <= 28 and not valid_nrb(digits):
                left = min(w.x for w in chunk)
                top = min(w.y for w in chunk)
                right = max(w.x + w.width for w in chunk)
                bottom = max(w.y + w.height for w in chunk)
                yield row_index, start, end, digits, (left, top, right, bottom), (x_min, x_max)
            start = end


def read_account_crops(positions, bitmap, api_type, data):
    crops = list(islice(account_crops(positions), 6))
    if not crops:
        return positions
    rows = [list(row) for row in positions]
    with api_type(path=str(data), lang="pol", psm=7) as api:
        api.SetVariable("tessedit_char_whitelist", "0123456789")
        api.SetImageBytes(bytes(bitmap.buffer), bitmap.width, bitmap.height, bitmap.n_channels, bitmap.stride)
        # Work right to left so replacing a run preserves the remaining indices.
        for row, start, end, original, (left, top, right, bottom), (x_min, x_max) in reversed(crops):
            height = bottom - top
            limit = bitmap.width if x_max is None else min(bitmap.width, x_max)
            readings = []
            for margin in (.25, .6):
                x = max(x_min, left - round(height * margin))
                y = max(0, top - round(height * .3))
                w = min(limit, right + round(height * margin)) - x
                h = min(bitmap.height, bottom + round(height * .3)) - y
                api.SetRectangle(x, y, w, h)
                value = "".join(api.GetUTF8Text().split())
                if not valid_nrb(value) or SequenceMatcher(None, original, value).ratio() < .90:
                    break
                readings.append(value)
            if len(readings) == 2 and readings[0] == readings[1]:
                rows[row][start:end] = [Word(left, top, right - left, height, readings[0])]
    return tuple(tuple(row) for row in rows)


def confirm_numeric_boxes(boxes, bitmap, api_type, data):
    if not boxes:
        return ()
    checked = []
    with api_type(path=str(data), lang="pol", psm=7) as line_api:
        line_api.SetImageBytes(bytes(bitmap.buffer), bitmap.width, bitmap.height, bitmap.n_channels, bitmap.stride)
        for key, value, (x, y, width, height) in boxes:
            alphabet = "0123456789.,-+ " if key == "kwota" else ""
            line_api.SetVariable("tessedit_char_whitelist", alphabet)
            for margin in (.30, .65):
                dx, dy = round(height * margin), round(height * .4)
                left, top = max(0, x - dx), max(0, y - dy)
                right, bottom = min(bitmap.width, x + width + dx), min(bitmap.height, y + height + dy)
                line_api.SetRectangle(left, top, right - left, bottom - top)
                token = line_api.GetUTF8Text().strip()
                if line_api.MeanTextConf() < 75 or token_value(token, key) != value:
                    break
            else:
                checked.append((key, value))
    return tuple(checked)


@dataclass(frozen=True)
class LocalOCR:
    document_type: type
    api_type: Callable
    data: Path

    def __call__(self, path, limit, *, start=0):
        return recognize(self.document_type, self.api_type, self.data, path, limit, start=start)

    def oriented_pages(self, path, limit, *, start=0):
        return recognize(self.document_type, self.api_type, self.data, path, limit, start=start, angles=True)

    def transfer_views(self, path, orientations):
        try:
            return self._transfer_views(path, orientations)
        except (OSError, ValueError, RuntimeError) as exc:
            logging.warning("Dodatkowy odczyt skanu przelewu: %s", type(exc).__name__)
            return []

    def _transfer_views(self, path, orientations):
        views = []
        with closing(self.document_type(path)) as pdf, self.api_type(path=str(self.data), lang="pol") as api:
            api.SetVariable("user_defined_dpi", "180")
            for index, rotation in orientations:
                with closing(pdf[index]) as page:
                    chosen = self._page_views(page, index, rotation, api)
                    # Automatic page segmentation can read upright text after rotating the bitmap.
                    # Fixed segmentation needs an upright page if the first orientation yielded no fields.
                    if rotation and not recovered_numbers(chosen):
                        upright = self._page_views(page, index, 0, api)
                        if recovered_numbers(upright):
                            chosen = upright
                    views.extend(chosen)
        return views

    def _page_views(self, page, index, rotation, api):
        views = []
        # PSM 6 reads a single block; PSM 11 locates sparse words separately.
        for mode, factor in ((6, 2.5), (11, 3.0)):
            scale = min(factor, 2600 / max(page.get_size()))
            with closing(page.render(scale=scale, rotation=rotation, grayscale=True)) as bitmap:
                api.SetPageSegMode(mode)
                api.SetImageBytes(bytes(bitmap.buffer), bitmap.width, bitmap.height,
                                  bitmap.n_channels, bitmap.stride)
                text = api.GetUTF8Text()
                tsv = api.GetTSVText(0)
                positions = word_rows(tsv)
                view = ScanView(index + 1, text, row_text(positions), positions=positions)
                views.append(view)
                if mode == 11:
                    missing = {"kwota", "data_operacji"} - recovered_numbers(views).keys()
                    boxes = numeric_boxes(tsv, view.rows, missing)
                    checked = confirm_numeric_boxes(boxes, bitmap, self.api_type, self.data)
                    positions = read_account_crops(positions, bitmap, self.api_type, self.data)
                    views[-1] = replace(view, verified=checked, positions=positions)
        return views


def recognize(document_type, api_type, data, path, limit, *, start=0, angles=False):
    with closing(document_type(path)) as pdf, api_type(path=str(data), lang="pol") as api:
        api.SetVariable("user_defined_dpi", "180")
        for index in range(start, limit):
            with closing(pdf[index]) as page:
                scale = min(2.5, 2200 / max(page.get_size()))
                best, selected_angle = "", 0
                for angle in (0, 90, 270, 180):
                    with closing(page.render(scale=scale, rotation=angle, grayscale=True)) as bitmap:
                        api.SetImageBytes(bytes(bitmap.buffer), bitmap.width, bitmap.height,
                                          bitmap.n_channels, bitmap.stride)
                        text = api.GetUTF8Text()
                        if len(text) > len(best):
                            best, selected_angle = text, angle
                        if len(text.split()) >= 8 and api.MeanTextConf() >= 55:
                            if text == best:
                                best = refine_bank_reference(text, api, bitmap, api_type, data)
                            break
                yield (index, best, selected_angle) if angles else (index, best)
