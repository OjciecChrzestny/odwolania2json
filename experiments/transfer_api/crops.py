"""Build a page of numbered numeric crops. Only these pixels may leave the VPS."""
import io
import re
import unicodedata
from contextlib import closing

import pypdfium2 as pdfium
from PIL import Image, ImageDraw
from tesserocr import PyTessBaseAPI

# Keep punctuation so account numbers, references and prose cannot qualify as a cell.
DIGIT = r"[0-9OoIl]"
AMOUNT = re.compile(rf"[-+−]?(?:{DIGIT}{{1,8}}|{DIGIT}{{1,3}}(?:[.']{DIGIT}{{3}})+)[,.]{DIGIT}{{2}}")
DATE = re.compile(rf"(?:{DIGIT}{{4}}[-./]{DIGIT}{{1,2}}[-./]{DIGIT}{{1,2}}|{DIGIT}{{1,2}}[-./]{DIGIT}{{1,2}}[-./]{DIGIT}{{4}})")
LABELS = {
    "kwota": "kwota", "wartosc": "wartosc", "amount": "amount",
    "data": "data", "date": "date", "operacji": "operacji", "transakcji": "transakcji",
    "wykonania": "wykonania", "realizacji": "realizacji", "ksiegowania": "ksiegowania",
    "obciazenia": "obciazenia", "booking": "booking", "execution": "execution",
    "wydruku": "wydruku", "wystawienia": "wystawienia", "wygenerowania": "wygenerowania",
    "oplata": "oplata", "prowizja": "prowizja", "saldo": "saldo", "pln": "PLN", "zl": "PLN",
}


def label(text):
    ascii_text = unicodedata.normalize("NFKD", text.lower().replace("ł", "l"))
    return LABELS.get("".join(c for c in ascii_text if "a" <= c <= "z"))


def ocr_rows(tsv):
    rows = {}
    for line in tsv.splitlines():
        word = line.split("\t", 11)
        if len(word) == 12 and word[0] == "5" and word[-1].strip():
            x, y, w, h = map(int, word[6:10])
            if w > 0 and h > 0:
                rows.setdefault(tuple(word[1:5]), []).append((x, y, w, h, word[-1].strip()))
    return [sorted(words) for words in rows.values()]


def cells(tsv, field):
    result = []
    pattern = AMOUNT if field == "kwota" else DATE
    for words in ocr_rows(tsv):
        labels = sorted({value for word in words if (value := label(word[-1]))})
        # A long run of separate number groups usually represents an account.
        if sum(bool(re.fullmatch(r"[0-9]{4}", w[-1])) for w in words) >= 4:
            continue
        for i, (x, y, width, height, token) in enumerate(words):
            token = token.strip("()[]|:;")
            if not pattern.fullmatch(token) or len(re.findall(r"[0-9]", token)) < 2:
                continue
            left = x
            if field == "kwota" and i:
                px, py, pw, ph, prefix = words[i - 1]
                if re.fullmatch(r"[0-9]{1,3}", prefix) and 0 <= x - px - pw < .7 * height:
                    left = px
            result.append(((left, y, x + width, y + height), labels))
    return result


def same_cell(a, b):
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = min((z[2] - z[0]) * (z[3] - z[1]) for z in (a, b))
    return overlap >= .7 * area


def numeric_panel(path, field, tessdata):
    with closing(pdfium.PdfDocument(path)) as pdf, closing(pdf[0]) as page:
        scale = min(3.0, 2300 / max(page.get_size()))
        with closing(page.render(scale=scale, grayscale=True)) as bitmap:
            data = bytes(bitmap.buffer)
            image = Image.frombytes("L", (bitmap.width, bitmap.height), data, "raw", "L", bitmap.stride)
            groups = []
            with PyTessBaseAPI(path=str(tessdata), lang="pol") as api:
                api.SetVariable("user_defined_dpi", "180")
                for mode in (6, 11):
                    api.SetPageSegMode(mode)
                    api.SetImageBytes(data, bitmap.width, bitmap.height, bitmap.n_channels, bitmap.stride)
                    for box, labels in cells(api.GetTSVText(0), field):
                        match = next((g for g in groups if same_cell(g[0], box)), None)
                        if match is None:
                            groups.append((box, set(labels)))
                        else:
                            match[1].update(labels)
    groups.sort(key=lambda g: (g[0][1], g[0][0]))
    if not groups or len(groups) > 12:
        return None, []
    panel = Image.new("L", (560, 78 * len(groups)), 255)
    draw = ImageDraw.Draw(panel)
    evidence = []
    for i, (box, labels) in enumerate(groups, 1):
        cut = image.crop(box)
        factor = min(63 / cut.height, 480 / cut.width)
        cut = cut.resize((max(1, round(cut.width * factor)), max(1, round(cut.height * factor))), Image.Resampling.BICUBIC)
        top = (i - 1) * 78
        draw.text((8, top + 23), str(i), fill=0, font_size=22)
        panel.paste(cut, (55, top + (78 - cut.height) // 2))
        evidence.append({"row": i, "labels": sorted(labels), "page": 1, "box": box, "render_scale": scale})
    stream = io.BytesIO()
    panel.save(stream, format="PNG")
    return stream.getvalue(), evidence
