"""Read a transfer title within the field and page that contain it."""
import re
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from statistics import median

from .bank_scan import word_rows

from .model import FLAGS
from .operations import normalize


TITLE = "przelew_bankowy.tytul"

_FIELD = (
    r"(?:Data (?:operacji|transakcji|realizacji|wykonania|księgowania|waluty|wydruku|wystawienia|nadania)|"
    r"Kwota(?: (?:operacji|przelewu|transakcji))?|Wartość(?: operacji)?|Waluta|"
    r"(?:Nr\.?|Numer|Identyfikator|ID) (?:operacji|transakcji|przelewu|referencyjny|referencji)|"
    r"Nr ref\.?|Referencje (?:banku|klienta|klientów)|"
    r"(?:Typ|Rodzaj|Kod|Status|Stan)(?: (?:i podtyp|operacji|produktu|przelewu|transakcji|zlecenia))?|"
    r"Opis (?:kodu )?(?:operacji|transakcji)|Dodatkowa treść|Kanał(?: zlecenia)?|"
    r"(?:Z|Na) rachun(?:ku|ek)|Rachunek (?:nadawcy|odbiorcy|beneficjenta|obciążany|uznawany)|"
    r"(?:Dane )?(?:Nadawca|Odbiorca|Płatnik|Beneficjent|Zleceniodawca)|"
    r"(?:Transaction|Transfer|Execution|Booking) (?:date|status|reference|ID)|"
    r"(?:Transfer )?Amount|Currency|Reference number|Account number|Payer|Beneficiary)"
)
_COLUMN = re.compile(_FIELD + r"\s*:?", re.I)
_LABELLED_FIELD = re.compile(_FIELD + r"[ \t]*:", re.I)
_NEXT_FIELD = re.compile(
    _FIELD + r"(?=[ \t:|]|$)|"
    r"(?:Opłata|Prowizja)(?=[ \t]*[:|]|[ \t]+[+-]?\d|$)|"
    r"(?:Strona|Page)(?=[ \t]+[+\d]|[ \t]*[:|]|$)|"
    r"(?:Szczegóły operacji|Zrealizowano|Potwierdzenie (?:wykonania |realizacji )?przelewu|"
    r"(?:Dokument|Potwierdzenie|Wydruk)\b[^\n]{0,100}\b(?:sporządzon\w*|wygenerowan\w*|"
    r"wydrukowan\w*|nie wymaga|podpisu|opieczętowani\w*)|"
    r"Bank\b[^\n]{0,80}\b(?:potwierdza|informuje|nie ponosi|siedzibą|S\.?A\.?)|"
    r"(?:Ten dokument|This document|Wydruk z systemu)\b|[-=_]{3,})(?=\W|$)",
    re.I,
)
_INLINE_FIELD = re.compile(r"(?:[ \t]*\|[ \t]*|[ \t]+)(?=" + _FIELD + r"[ \t]*:)", re.I)
_OPERATION_DESCRIPTION = re.compile(
    r"(?:polecenie przelewu|przelew (?:krajowy|przychodzący|wychodzący|wewnętrzny)|"
    r"(?:krajowa )?płatność (?:wychodząca|przychodząca|kartą)|(?:incoming|outgoing) (?:bank )?transfer)"
    r"[ \t.]*",
    re.I,
)
_QUOTED = re.compile(r'^[„“"]([^”"]*)[”"]\.?')
_PLACEHOLDER = re.compile(r"(?:[-–—._]+|brak|n/?a)", re.I)
_CONNECTOR = re.compile(r"^(?:a|i|oraz|dla|do|na|od|po|w|we|z|za|ze)[ \t]+")
_REFERENCE_TOKEN = re.compile(r"(?=[A-Z0-9./_-]*[A-Z])(?=[A-Z0-9./_-]*[0-9])[A-Z0-9][A-Z0-9./_-]*")


def present(value):
    return bool(value) and not _PLACEHOLDER.fullmatch(value)


def row_value(text, patterns, *, inline=False):
    text = text.strip()
    if text.startswith(("„", "“", '"')):
        return text, False
    if inline:
        boundary = _LABELLED_FIELD.match(text) or _COLUMN.fullmatch(text)
    else:
        boundary = _NEXT_FIELD.match(text)
    if boundary or any(pattern.fullmatch(text) for pattern in patterns):
        return "", True
    next_field = _INLINE_FIELD.search(text)
    if next_field:
        return text[:next_field.start()].rstrip(), True
    return text, False


def detached_continuation(lines, patterns):
    # OCR can put an empty line inside a field. A separated fragment must
    # continue the title and end at a recognizable field boundary.
    block = []
    closed = False
    for raw in lines:
        if not raw.strip():
            if block:
                terminator = next((line for line in lines if line.strip()), "")
                value, closed = row_value(terminator, patterns)
                closed = closed and not value
                break
            continue
        value, closed = row_value(raw, patterns)
        if present(value):
            block.append(value)
        if closed or not present(value):
            break
    if closed and block and (_CONNECTOR.match(block[0]) or all(
        _REFERENCE_TOKEN.fullmatch(token) for row in block for token in row.split()
    )):
        return block
    return []


def wrapped_value(lines, index, initial, patterns):
    following = iter(lines[index + 1:])
    inline = bool(initial.strip())
    first = initial if inline else next((line for line in following if line.strip()), "")
    first, closed = row_value(first, patterns, inline=inline)
    if not present(first):
        return None
    parts = [first]
    quoted = first.startswith(("„", "“", '"'))
    for raw in following:
        if closed or quoted and _QUOTED.match(" ".join(parts)):
            break
        if not raw.strip():
            parts.extend(detached_continuation(following, patterns))
            break
        value, closed = row_value(raw, patterns)
        if not present(value):
            break
        parts.append(value)
    value = " ".join(parts)
    enclosed = _QUOTED.match(value)
    value = normalize(enclosed[1] if enclosed else value, "text")
    return value if present(value) else None


def column_title(lines, index, patterns):
    labels = [cell.strip() for cell in lines[index].split("|")]
    if len(labels) < 2:
        return None
    matches = [i for i, label in enumerate(labels)
               if any((match := pattern.fullmatch(label)) and not match[1] for pattern in patterns)]
    if len(matches) != 1:
        return None
    title_index, = matches
    if not all(_COLUMN.fullmatch(label) for i, label in enumerate(labels) if i != title_index):
        return None
    parts = []
    for row in lines[index + 1:]:
        cells = [cell.strip() for cell in row.split("|")]
        if len(cells) != len(labels) or any(_COLUMN.fullmatch(cell) for cell in cells):
            break
        if parts and any(cell for i, cell in enumerate(cells) if i != title_index):
            break
        title, closed = row_value(cells[title_index], patterns, inline=True)
        if not present(title):
            break
        parts.append(title)
        if closed:
            break
    return labels[title_index], normalize(" ".join(parts), "title")


def page_title(layout, pattern, patterns, page, start):
    lines = page.split("\n")
    offset = start
    empty = None
    for index, line in enumerate(lines):
        columns = column_title(lines, index, patterns)
        if columns:
            label, value = columns
            candidate = pattern.fullmatch(label)
        else:
            candidate = pattern.fullmatch(line)
            if candidate:
                value = wrapped_value(lines, index, candidate[1], patterns)
        if candidate:
            if value and not (layout == "description" and _OPERATION_DESCRIPTION.fullmatch(value)):
                return value, offset
            if layout == "title" and empty is None:
                empty = (None, offset)
        offset += len(line) + 1
    return empty


def apply_transfer_title(result, rules):
    layout_rules = [(rule, re.compile(rule["pattern"], FLAGS)) for rule in rules if rule.get("title_layout")]
    if not layout_rules:
        return
    existing = result.evidence.get(TITLE)
    if existing and existing["rule"] not in {rule["name"] for rule, _ in layout_rules}:
        return
    result.data["przelew_bankowy"]["tytul"] = None
    result.evidence.pop(TITLE, None)
    patterns = [pattern for _, pattern in layout_rules]
    for rule, pattern in layout_rules:
        start = 0
        for page in result.document.text.split("\f"):
            found = page_title(rule["title_layout"], pattern, patterns, page, start)
            if found is not None:
                value, offset = found
                result.put(("przelew_bankowy", "tytul"), value, offset, rule["name"])
                apply_scan_title(result, rules)
                return
            start += len(page) + 1
    apply_scan_title(result, rules)


_SCAN_SECTION = re.compile(
    r"^(?:dane (?:nadawcy|odbiorcy|zleceniodawcy|beneficjenta)|"
    r"nazwa(?: i adres)?(?: (?:nadawcy|odbiorcy|zleceniodawcy|beneficjenta)\b|\s*:)|"
    r"recipient details|payer details|sender details|account details)(?=\W|$)",
    re.I,
)


def cells(words):
    """Split a physical row at horizontal gaps substantially wider than a word space."""
    if not words:
        return ()
    height = median(word.height for word in words)
    parts = [[words[0]]]
    for previous, word in zip(words, words[1:]):
        if word.x - previous.x - previous.width > 2.5 * height:
            parts.append([])
        parts[-1].append(word)
    return parts


def cell_text(cell):
    parts = [cell[0].text]
    for before, word in zip(cell, cell[1:]):
        gap = word.x - before.x - before.width
        if word.text in ".,;:?!)]}" and gap <= .34 * before.height:
            parts[-1] += word.text
        else:
            parts.append(word.text)
    return " ".join(parts)


def word_baseline(word, height):
    # Clip the effective descent of boxes containing an oversized OCR artifact.
    return word.middle + min(word.height, height) / 2


def punctuation_fits(mark, row, height):
    left = min((mark.x - word.x - word.width for word in row if word.x + word.width <= mark.x),
               default=float("inf"))
    if left <= .34 * height:
        return True
    if mark.text not in ("-", "–", "—", "/"):
        return False
    right = min((word.x - mark.x - mark.width for word in row if word.x >= mark.x + mark.width),
                default=float("inf"))
    return max(left, right) <= 1.6 * height


def deskewed_rows(positions):
    words = [word for row in positions for word in row if word.height > 0]
    if not words:
        return ()
    height = median(word.height for word in words)
    typical = [word for word in words if word.height >= .4 * height]

    slopes = []
    for row in positions:
        for cell in cells(row):
            for first, last in combinations(cell, 2):
                distance = last.x - first.x
                if distance < 6 * height or min(first.height, last.height) < .55 * height:
                    continue
                slope = (word_baseline(last, height) - word_baseline(first, height)) / distance
                if abs(slope) < .14:
                    slopes.append(slope)
    slope = median(slopes) if len(slopes) >= 4 else 0

    def level(word):
        return word_baseline(word, height) - slope * word.x

    clustered = []
    levels = []
    for word in sorted(typical, key=level):
        y = level(word)
        if not clustered or y - median(levels[-1]) > .46 * height:
            clustered.append([])
            levels.append([])
        clustered[-1].append(word)
        levels[-1].append(y)
    # Retain a small punctuation token only when it touches part of a text row.
    for mark in words:
        if mark.height >= .4 * height or mark.text.isalnum():
            continue
        neighbors = [(abs(level(mark) - median(ys)), row) for row, ys in zip(clustered, levels)
                     if abs(level(mark) - median(ys)) <= .78 * height and punctuation_fits(mark, row, height)]
        if neighbors:
            min(neighbors, key=lambda item: item[0])[1].append(mark)
    return tuple((median(ys), cells(sorted(row, key=lambda word: word.x)))
                 for row, ys in zip(clustered, levels))


def scan_boundary(text, patterns):
    return (_NEXT_FIELD.match(text) or _SCAN_SECTION.match(text)
            or any(pattern.fullmatch(text) for pattern in patterns))


_CURRENCY_VALUE = re.compile(r"[+-−]?\d(?:[\d., ]*\d)?\s*(?:PLN|EUR|USD|GBP|CHF|zł)", re.I)
_BANK_COLUMN = re.compile(r"(?:Data|Kwota|Waluta|Status|Amount|Date)[.:]?", re.I)


def visual_match(pattern, text):
    match = pattern.fullmatch(text)
    if not match and text.endswith("."):
        bare = pattern.fullmatch(text[:-1])
        if bare and not bare[1]:
            return bare
    return match


def scan_continuation(rows, level, anchors, height, patterns):
    left = min(anchors) - 1.5 * height
    right = max(anchors) + 1.5 * height
    parts = []
    for y, row in rows:
        if y - level > 2.8 * height:
            break
        aligned = [cell for cell in row if left <= cell[0].x <= right]
        if len(aligned) != 1:
            break
        cell, = aligned
        if any(scan_boundary(cell_text(other), patterns) for other in row if other[0].x <= cell[0].x):
            break
        value, closed = row_value(cell_text(cell), patterns, inline=True)
        if not present(value) or _CURRENCY_VALUE.fullmatch(value):
            break
        parts.append((value, cell))
        level = y
        if closed or _QUOTED.match(" ".join(fragment for fragment, _ in parts)):
            break
    return parts


@dataclass(frozen=True)
class VisualTitle:
    value: str
    supported_spaces: frozenset[int]


def physical_spaces(value, source_cells):
    separated_pairs = {
        (before.text, after.text)
        for cell in source_cells for before, after in zip(cell, cell[1:])
        if .3 * min(before.height, after.height) <= after.x - before.x - before.width
    }
    tokens = value.split()
    offset = 0
    supported = set()
    for before, after in zip(tokens, tokens[1:]):
        offset += len(before)
        if (before, after) in separated_pairs:
            supported.add(offset)
    return frozenset(supported)


def visual_title(positions, layout_rules):
    """Read a title from positioned OCR words on one physical page."""
    rows = deskewed_rows(positions)
    patterns = [pattern for _, pattern in layout_rules]
    for rule, pattern in layout_rules:
        values = {}
        for index, (level, row) in enumerate(rows):
            for column, cell in enumerate(row):
                label = cell_text(cell)
                match = visual_match(pattern, label)
                if not match:
                    continue
                if rule["title_layout"] == "description" and any(
                    _BANK_COLUMN.fullmatch(cell_text(other)) for other in row if other is not cell
                ):
                    continue
                height = median(word.height for word in cell)
                following = row[column + 1:]
                initial, closed = row_value(match[1], patterns, inline=True)
                value_cell = cell
                if not match[1].strip() and following:
                    adjacent = cell_text(following[0])
                    if not scan_boundary(adjacent, patterns) and not _CURRENCY_VALUE.fullmatch(adjacent):
                        initial, closed = row_value(adjacent, patterns, inline=True)
                        value_cell = following[0]
                anchors = (value_cell[0].x,)
                if initial and value_cell is cell:
                    prefix_words = len(label[:match.start(1)].split())
                    if prefix_words < len(cell):
                        anchors += (cell[prefix_words].x,)
                parts = [(initial, value_cell)] if present(initial) else []
                if not closed and not _QUOTED.match(initial) and (parts or not match[1].strip()):
                    parts.extend(scan_continuation(rows[index + 1:], level, anchors, height, patterns))
                value = normalize(" ".join(fragment for fragment, _ in parts), "title")
                if present(value) and not _CURRENCY_VALUE.fullmatch(value) and not (
                    rule["title_layout"] == "description" and _OPERATION_DESCRIPTION.fullmatch(value)
                ):
                    spaces = physical_spaces(value, (source for _, source in parts))
                    values.setdefault(value, set()).update(spaces)
        if values:
            if len(values) == 1:
                value, spaces = next(iter(values.items()))
                return VisualTitle(value, frozenset(spaces))
            return None
    return None


def alnum(value):
    return "".join(character for character in value if character.isalnum())


def case_supported_by_primary(candidates, document):
    if len(candidates) != 2:
        return None
    left, right = candidates
    if left[0] != right[0] or left[1].casefold() != right[1].casefold():
        return None
    page = left[0]
    start = document.starts[page - 1][0]
    stop = document.starts[page][0] if page < len(document.starts) else len(document.text)
    reading = alnum(document.text[start:stop])
    supported = [candidate for candidate in candidates if alnum(candidate[1]) in reading]
    return supported[0] if len(supported) == 1 else None


def whitespace_offsets(value):
    offset = 0
    for word in value.split()[:-1]:
        offset += len(word)
        yield offset


def complementary_spaces(observations):
    # The readings must agree on every non-whitespace character. Each must
    # contribute a distinct, spatially supported boundary from the same page.
    variants = {}
    for page, reading in observations:
        variants.setdefault((page, reading.value), set()).update(reading.supported_spaces)
    if len(variants) != 2:
        return None
    (left_page, left), (right_page, right) = variants
    compact = "".join(left.split())
    if left_page != right_page or compact != "".join(right.split()):
        return None
    a, b = set(whitespace_offsets(left)), set(whitespace_offsets(right))
    left_only, right_only = a - b, b - a
    if not left_only or not right_only:
        return None
    if not left_only <= variants[(left_page, left)] or not right_only <= variants[(right_page, right)]:
        return None
    stops = [0, *sorted(a | b), len(compact)]
    return left_page, " ".join(compact[first:last] for first, last in zip(stops, stops[1:]))


def apply_scan_title(result, rules, *, views=(), primary_document=None):
    """Use OCR geometry without rendering another page or assigning a native title."""
    layout_rules = [(rule, re.compile(rule["pattern"], FLAGS)) for rule in rules if rule.get("title_layout")]
    if not layout_rules:
        return
    recorded = result.evidence.get(TITLE)
    allowed = {rule["name"] for rule, _ in layout_rules} | {"ocr_tytul_pola"}
    if recorded and recorded["rule"] not in allowed:
        return
    document = result.document
    reading = primary_document if primary_document is not None else document
    existing = result.data["przelew_bankowy"]["tytul"]
    if existing and (recorded is None or recorded.get("source") == "text"):
        return
    page = recorded.get("page") if existing else None
    original = None
    if reading.ocr_layout_tsv and len(reading.starts) == len(document.starts) == 1 and page in (None, 1):
        original = visual_title(word_rows(reading.ocr_layout_tsv), layout_rules)
    observations = [(view.page, title) for view in views
                    if view.positions and 1 <= view.page <= len(document.starts) and page in (None, view.page)
                    if (title := visual_title(view.positions, layout_rules))]
    if original is not None:
        observations.append((1, original))
    candidates = Counter((number, title.value) for number, title in observations)
    confirmed = {value for value, count in candidates.items() if count >= 2}
    if not confirmed:
        corroborated = complementary_spaces(observations)
        if corroborated is None and original is None:
            corroborated = case_supported_by_primary(tuple(candidates), reading)
        if corroborated:
            confirmed.add(corroborated)
    if len(confirmed) == 1:
        chosen_page, title = next(iter(confirmed))
    elif not confirmed and original is not None:
        title = original.value
        if existing and not (title.startswith(existing + " ") or existing.startswith(title + " ")
                             or alnum(title) == alnum(existing) or _SCAN_SECTION.match(existing)):
            return
        chosen_page = 1
    else:
        return
    if title != existing:
        result.put(("przelew_bankowy", "tytul"), title, document.starts[chosen_page - 1][0],
                   "ocr_tytul_pola", source="ocr")
