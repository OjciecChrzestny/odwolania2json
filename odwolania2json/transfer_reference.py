"""Read a missing transaction reference from labelled bank OCR rows."""
import re

from .bank_scan import word_rows
from .transfer import REF, REF_DAILY_RULE, reference_value

PATH = ("przelew_bankowy", "numer_transakcji")
RULE = "ocr_referencja_w_polu_transakcji"
OTHER_FIELD = re.compile(
    r"(?:(?:numer|nr|id|identyfikator|kod) (?:referencyjny )?"
    r"(?:dokumentu|wydruku|potwierdzenia|faktury|sprawy|rachunku|klienta)"
    r"|rachunek|data|kwota|saldo|opłata|opis|tytuł|status|"
    r"(?:print|document|invoice|case|account|receipt) (?:id|number|reference)|date|amount|title)\b",
    re.I,
)
QUALIFIER = re.compile(r"^\s*(?:dokumentu|wydruku|potwierdzenia|faktury|sprawy|rachunku|klienta)\b", re.I)
QUALIFIED_REFERENCE = re.compile(r"^(?:Nr|Numer) referencyjny (?:transakcji|operacji)\b", re.I)
WRAPPED_FIRST = re.compile(r"(?:numer|nr)\.?:?", re.I)
WRAPPED_SECOND = re.compile(r"transakcji:?", re.I)
GRAPHIC = re.compile(r"[^\w\s]")
MASKED = re.compile(r"(?:\*|•|…|X{2,}[ ./_-]*[0-9]|[0-9][ ./_-]*X{2,})", re.I)


def label_end(row, start, length):
    while length > 0:
        length -= len(row[start].text) + 1
        start += 1
    return start


def fields(row):
    """Find complete transaction and unrelated headings along a visual row."""
    start = 0
    while start < len(row):
        following = " ".join(word.text for word in row[start:])
        qualified = QUALIFIED_REFERENCE.match(following)
        anchor = qualified or REF.match(following)
        if anchor and (qualified or not anchor["daily"]) and not QUALIFIER.match(following[anchor.end():]):
            # Keep the last word consumed by the heading, including a stand-alone colon.
            end = label_end(row, start, anchor.end())
            if end < len(row) and row[end].text == ":":
                end += 1
            yield start, end, bool(qualified or anchor["bank"]), bool(qualified)
            start = end
        else:
            other = OTHER_FIELD.match(following)
            if other:
                end = label_end(row, start, other.end())
                yield start, end, None, False
                start = end
            else:
                start += 1


def labelled_value(words, bank_reference):
    text = " ".join(word.text for word in words).lstrip(" \t:.-")
    if MASKED.search(text):
        return None
    return reference_value(text, bank_reference=bank_reference)


def wrapped_references(row, below):
    """Bind a two-line left-hand label to the value beside its upper line."""
    for i, start in enumerate(row):
        if not WRAPPED_FIRST.fullmatch(start.text) or any(not GRAPHIC.fullmatch(w.text) for w in row[:i]):
            continue
        aligned = [word for word in below if abs(word.x - start.x) <= max(word.height, start.height)]
        if len(aligned) != 1 or not WRAPPED_SECOND.fullmatch(aligned[0].text):
            continue
        lower = aligned[0]
        if any(word != lower and not GRAPHIC.fullmatch(word.text) for word in below):
            continue
        if not 0 < lower.middle - start.middle <= 2 * max(lower.height, start.height):
            continue
        tokens = [word for word in row[i + 1:] if word.text != "|"]
        if len(tokens) == 1 and tokens[0].x >= start.x + start.width:
            value = labelled_value(tokens, bank_reference=False)
            if value is not None:
                yield value


def row_references(rows):
    for i, row in enumerate(rows):
        if i + 1 < len(rows):
            yield from wrapped_references(row, rows[i + 1])
        headings = list(fields(row))
        for heading, (start, end, bank_reference, qualified) in enumerate(headings):
            if bank_reference is None:
                continue
            stop = headings[heading + 1][0] if heading + 1 < len(headings) else len(row)
            left = row[start]
            if start and heading == 0:
                previous = row[start - 1]
                if not qualified or left.x - previous.x - previous.width < 2 * left.height:
                    continue
            if end < stop:
                value = labelled_value(row[end:stop], bank_reference)
            elif qualified or len(headings) > 1:
                right = row[stop].x if stop < len(row) else float("inf")
                tolerance = max(left.height, row[end - 1].height)
                value = None
                for following in rows[i + 1:i + (3 if qualified else 2)]:
                    column = [word for word in following if left.x - tolerance <= word.x < right - tolerance]
                    if not column:
                        continue
                    upper_bound = left.x + tolerance if qualified else row[end - 1].x + row[end - 1].width + tolerance
                    if (0 < column[0].middle - left.middle <= (3.5 if qualified else 3) * tolerance
                            and column[0].x <= upper_bound):
                        value = labelled_value(column, bank_reference)
                    break
            else:
                continue
            if value is not None:
                yield value


def apply_scan_reference(result, views=()):
    """Fill a missing reference only when the readings agree on its physical page."""
    field = ".".join(PATH)
    current = result.evidence.get(field, {})
    if result.data[PATH[0]][PATH[1]] is not None and current.get("rule") != REF_DAILY_RULE:
        return
    document = result.document
    readings = [(view.page, view.positions) for view in views if view.positions]
    if document.ocr_layout_tsv and len(document.starts) == 1:
        readings.append((1, word_rows(document.ocr_layout_tsv)))
    candidates = {(page, value) for page, rows in readings if 1 <= page <= len(document.starts)
                  for value in row_references(rows)}
    if len(candidates) == 1:
        page, value = candidates.pop()
        result.put(PATH, value, document.starts[page - 1][0], RULE, source="ocr")
