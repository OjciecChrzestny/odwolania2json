"""Locate transfer dates with an explicit nearby field label on the same page."""
import re
import unicodedata

from odwolania2json.operations import MONTHS

DIGIT = r"[0-9OoIl]"
NUMERIC = re.compile(rf"(?:{DIGIT}{{4}}[-./]{DIGIT}{{1,2}}[-./]{DIGIT}{{1,2}}|{DIGIT}{{1,2}}[-./]{DIGIT}{{1,2}}[-./]{DIGIT}{{4}})")
PRIMARY = {"operacji", "transakcji", "realizacji", "wykonania", "obciazenia", "efektywna", "platnosci", "execution"}
BOOKING = {"ksiegowania", "booking"}
EXCLUDE = {"wygenerowano", "wygenerowania", "wygenerowany", "wydruku", "wydrukowano", "wydruk", "wystawienia",
           "wydania", "utworzenia", "zlecenia", "termin", "do", "urodzenia", "tytul", "tytulem", "saldo"}
DATE_LABELS = PRIMARY | BOOKING | {"data", "date"}


def folded(value):
    text = unicodedata.normalize("NFKD", value.casefold().replace("ł", "l"))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).strip(" \t.:;()")


MONTH_WORDS = {folded(word) for word in MONTHS}


def bounds(words):
    return (min(w[0] for w in words), min(w[1] for w in words),
            max(w[0] + w[2] for w in words), max(w[1] + w[3] for w in words))


def close_pair(a, b):
    return -.2 * max(a[3], b[3]) <= b[0] - a[0] - a[2] <= 1.15 * max(a[3], b[3])


def anchors(words):
    result = []
    for i, word in enumerate(words):
        role = folded(word[-1])
        if role in EXCLUDE:
            result.append((bounds([word]), role))
        if role not in PRIMARY | BOOKING:
            continue
        if i and folded(words[i - 1][-1]) in {"data", "date"} and close_pair(words[i - 1], word):
            result.append((bounds(words[i - 1:i + 1]), role))
        elif i + 1 < len(words) and folded(words[i + 1][-1]) == "date" and close_pair(word, words[i + 1]):
            result.append((bounds(words[i:i + 2]), role))
    return result


def date_words(words):
    for i, word in enumerate(words):
        token = word[-1].strip("[]()|:;")
        if NUMERIC.fullmatch(token) and sum(ch.isdigit() for ch in token) >= 4:
            yield [word]
        elif i + 2 < len(words) and re.fullmatch(r"[0-3]?[0-9]", token):
            month, year = words[i + 1:i + 3]
            if (folded(month[-1]) in MONTH_WORDS and re.fullmatch(r"20[0-9]{2}", year[-1])
                    and close_pair(word, month) and close_pair(month, year)):
                yield [word, month, year]


def distance(anchor, date):
    x, y, right, bottom = anchor
    dx = date[0] - right
    height = max(1, bottom - y, date[3] - date[1])
    center_difference = abs((y + bottom - date[1] - date[3]) / 2)
    if center_difference <= .6 * height and -.2 * height <= dx <= 32 * height:
        return (0, (max(0, dx) + center_difference) / height)
    dy = date[1] - bottom
    offset = abs(date[0] - x)
    if -.15 * height <= dy <= 2.8 * height and offset <= max(1.7 * height, .55 * (right - x)):
        return (1, (max(0, dy) + offset) / height)
    return None


def intervenes(anchor, date, all_words, orientation):
    """A value from a neighbouring field cannot inherit this anchor."""
    for x, y, width, height, token in all_words:
        cx, cy = x + width / 2, y + height / 2
        if not any(ch.isalnum() for ch in token) or folded(token) in {"przelewu", "operacji", "dokumentu", "r"}:
            continue
        if orientation == 0:
            if anchor[2] < cx < date[0] and date[1] <= cy <= date[3]:
                return True
        elif anchor[3] < cy < date[1] and date[0] <= cx <= date[2]:
            return True
    return False


def date_cells(rows):
    all_words = [w for row in rows for w in row]
    roles = [a for row in rows for a in anchors(row)]
    candidates = []
    for row in rows:
        for pieces in date_words(row):
            box = bounds(pieces)
            nearby = [(dist, role, anchor) for anchor, role in roles
                      if (dist := distance(anchor, box)) is not None
                      and not intervenes(anchor, box, all_words, dist[0])]
            if not nearby:
                continue
            nearby.sort()
            dist, role, anchor = nearby[0]
            if role in EXCLUDE or any(r != role and d[0] == dist[0] and abs(d[1] - dist[1]) < .3
                                      for d, r, _ in nearby[1:]):
                continue
            # Keep each token's pixels separately. Padding retains faint strokes at a word boundary.
            rects = []
            for x, y, width, height, _ in pieces:
                pad = max(1, round(height * .12))
                rects.append((max(0, x - pad), max(0, y - pad), x + width + pad, y + height + pad))
            candidates.append((box, role, anchor, rects))
    return candidates
