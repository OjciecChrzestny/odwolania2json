"""Recover payment amounts and dates from the visual rows of a bank scan."""
import re
from collections import defaultdict
from dataclasses import dataclass
from math import isfinite
from statistics import median

from .operations import DATE, normalize


@dataclass(frozen=True)
class ScanView:
    page: int
    text: str
    rows: tuple
    verified: tuple = ()
    positions: tuple = ()


@dataclass(frozen=True)
class Word:
    x: int
    y: int
    width: int
    height: int
    text: str

    @property
    def middle(self):
        return self.y + self.height / 2


def word_rows(tsv):
    words = []
    for line in tsv.splitlines():
        item = line.split("\t", 11)
        if len(item) == 12 and item[0] == "5" and item[11].strip():
            words.append(Word(*map(int, item[6:10]), item[11].strip()))
    grouped = []
    for word in sorted(words, key=lambda w: (w.middle, w.x, w.height, w.text)):
        if grouped:
            row = grouped[-1]
            if abs(word.middle - median(w.middle for w in row)) <= .55 * max(word.height, median(w.height for w in row)):
                row.append(word)
                continue
        grouped.append([word])
    return tuple(tuple(sorted(row, key=lambda w: w.x)) for row in grouped)


def row_text(words):
    return tuple(" ".join(w.text for w in row) for row in words)


def visual_rows(tsv):
    return row_text(word_rows(tsv))


def primary_scan_view(document):
    """Keep the single-page primary OCR geometry tied to its own text."""
    if len(document.starts) != 1 or not document.ocr_layout_tsv:
        return None
    try:
        positions = word_rows(document.ocr_layout_tsv)
    except ValueError:
        return None
    if not positions:
        return None
    text = document.text.removesuffix("\n\f\n")
    return ScanView(1, text, row_text(positions), positions=positions)


DATE_TOKEN = re.compile(r"(?<![\d./-])" + DATE + r"(?![\d./-])", re.I)
MONEY_TOKEN = re.compile(
    r"(?<![\d.,])[-−+]?(?:[0-9]{1,3}(?:[ .][0-9]{3})+|[0-9]+)[,.][ \t]*[0-9]{2}(?![\d.,])"
)
AMOUNT_LABEL = (
    r"(?:kwota|warto[śs][ćc]|(?:transfer )?amount)"
    r"(?: (?:operacji|przelewu|transakcji|w walucie rachunku|obci[ąa][żz]enia))?"
)
DATE_LABEL = r"(?:data (?:operacji|transakcji|realizacji|wykonania)|execution date|date of operation|transaction date)"
BOOKING_LABEL = r"(?:data ksi[ęe]gowania|booking date)"
OTHER_AMOUNT = (
    r"(?:(?:kwota |warto[śs][ćc] )?(?:prowizj\w*|op[łl]at[ayę]|sald[oa](?: po operacji)?"
    r"|kurs|nale[żz]no[śs]ci|do zap[łl]aty)|(?:available |account )?balance|fee|commission)"
)
OTHER_DATE = (
    r"(?:(?:data )?(?:wydruk\w*|wystawieni\w*|wygenerow\w*|utworzeni\w*)"
    r"|(?:data|dzie[ńn]) (?:waluty|zlecenia|wyci[ąa]gu)|(?:print|generation|value) date)"
)
LABELS = re.compile(
    rf"\b(?:(?P<other_amount>{OTHER_AMOUNT})|(?P<other_date>{OTHER_DATE})"
    rf"|(?P<execution>{DATE_LABEL})|(?P<booking>{BOOKING_LABEL})|(?P<amount>{AMOUNT_LABEL}))\b",
    re.I,
)
COLUMN = {
    "execution": ("data_operacji", 3),
    "booking": ("data_operacji", 2),
    "amount": ("kwota", 3),
    "other_date": ("data_operacji", 0),
    "other_amount": ("kwota", 0),
}
REFERENCE_COLUMN = re.compile(
    r"[ \t|;]+(?:nr\.?|numer|identyfikator) (?:referencyjn(?:y|ego) )?(?:operacji|transakcji|przelewu)$",
    re.I,
)
REFERENCE_CELL = re.compile(r"[ \t|;*]+(?=[A-Z0-9./_-]{1,64}$)(?=[A-Z0-9./_-]*[0-9])[A-Z0-9][A-Z0-9./_-]*", re.I)
POSTED_HEADER = re.compile(r"Data[ \t|]+Opis[ \t|]+Kwota", re.I)
POSTED_ROW = re.compile(r"Data operacji[ \t|:–—-]+przelew\b", re.I)
SPLIT_DATA = re.compile(rf"Data[ \t:|]+(?P<date>{DATE})[ \t|:]*", re.I)
SPLIT_ROLE = re.compile(r"(?:wykonania|realizacji)[ \t|:]*", re.I)
LABEL_GAP = re.compile(r"[\s|:;–—-]*")
BOOKING_ROW = re.compile(rf"^{BOOKING_LABEL}\b", re.I)
EXECUTION_ROW = re.compile(rf"^{DATE_LABEL}\b", re.I)
BOOKING_VALUE = re.compile(rf"^(?P<date>{DATE})(?=[ \t]|$)(?:[ \t|]*|[ \t|]+na rachunek\b.*)", re.I)
ORDER_DETAILS = re.compile(r"(?:dane|szczeg[oó][łl]y) zlecenia[ \t.:]*", re.I)
COMPLETED_ORDER = re.compile(
    r"^status(?: (?:operacji|transakcji|zlecenia|przelewu))?[\s.:'‘\"|;,-]{1,18}"
    r"(?:wykonan|zrealizowan|zaksi[ęe]gowan)[aye]\b",
    re.I | re.M,
)
PENDING_ORDER = re.compile(
    r"^status(?: (?:operacji|transakcji|zlecenia|przelewu))?[\s.:'‘\"|;,-]{1,18}"
    r"(?:oczekuj|planowan|zaplanowan|niewykonan|niezrealizowan|anulowan|odrzucon)\w*\b",
    re.I | re.M,
)
ORDER_MODE = re.compile(r"tryb realizacj[i.](?=[ \t]|$)", re.I)
ORDER_EXECUTION = re.compile(
    rf"\bda[tl]a wykonania[ \t|:]+(?P<date>{DATE}|\d{{1,2}}[ \t]+\d{{1,2}}[ \t]+20\d{{2}})[ \t|]*$",
    re.I,
)
NON_EXECUTED_DATE = re.compile(r"\b(?:planowan\w*|przewidywan\w*|oczekiwan\w*|ż[ąa]dan\w*|zlecon\w*|termin)\b", re.I)
SEPARATORS = re.compile(r"[\s|:;]*")
VALUE_SEPARATORS = re.compile(r"(?:[\s|:;]|PLN|zł|EUR|USD|GBP|CHF)*", re.I)


@dataclass(frozen=True)
class Number:
    key: str
    value: str | float | None
    start: int
    end: int


def money_value(token):
    value = normalize(token, "money")
    return abs(value) if value is not None and isfinite(value) else None


def number_tokens(line):
    dates = list(DATE_TOKEN.finditer(line))
    # Mask the entire date even when the calendar value is invalid. Preserve offsets.
    rest = DATE_TOKEN.sub(lambda match: " " * len(match[0]), line)
    tokens = [Number("data_operacji", normalize(m[0], "date"), *m.span()) for m in dates]
    tokens.extend(Number("kwota", money_value(m[0]), *m.span())
                  for m in MONEY_TOKEN.finditer(rest))
    return sorted(tokens, key=lambda item: item.start)


def numeric_row(line, tokens):
    current = 0
    for token in tokens:
        if not VALUE_SEPARATORS.fullmatch(line[current:token.start]):
            return False
        current = token.end
    return VALUE_SEPARATORS.fullmatch(line[current:]) is not None


def reference_table(header, values):
    """Remove an explicitly labelled trailing ID column from a PLN table."""
    label = REFERENCE_COLUMN.search(header)
    reference = REFERENCE_CELL.search(values)
    if not (label and reference):
        return header, values
    numeric = values[:reference.start()].rstrip()
    tokens = number_tokens(numeric)
    if (len(tokens) != 2 or [token.key for token in tokens] != ["kwota", "data_operacji"]
            or not re.fullmatch(r"[ \t]*PLN[ \t|;]*", numeric[tokens[0].end:tokens[1].start], re.I)):
        return header, values
    return header[:label.start()], numeric


def table_numbers(header, values):
    """Bind a complete numeric row to its recognised column headers."""
    header, values = reference_table(header, values)
    labels = list(LABELS.finditer(header))
    if len(labels) < 2 or not SEPARATORS.fullmatch(LABELS.sub("", header)):
        return []
    tokens = number_tokens(values)
    if len(tokens) != len(labels) or not numeric_row(values, tokens):
        return []
    columns = [COLUMN[label.lastgroup] for label in labels]
    order = [key for key, _ in columns]
    keys = [token.key for token in tokens]
    if keys != order:
        if len(set(keys)) != len(keys) or set(keys) != set(order):
            return []
        # A unique date and amount can also be distinguished by their types.
        by_key = {token.key: token for token in tokens}
        tokens = [by_key[key] for key in order]
    return [(priority, token) for (_, priority), token in zip(columns, tokens)
            if priority and token.value is not None]


def structured_numbers(line, following):
    for priority, token in table_numbers(line, following):
        yield 1, priority, token
    if SPLIT_ROLE.fullmatch(following) and (split := SPLIT_DATA.fullmatch(line)):
        if value := normalize(split["date"], "date"):
            yield 0, 3, Number("data_operacji", value, *split.span("date"))
    if not (POSTED_HEADER.fullmatch(line) and POSTED_ROW.match(following)):
        return
    if any(label.lastgroup == "other_amount" for label in LABELS.finditer(following)):
        return
    amounts = [token for token in number_tokens(following) if token.key == "kwota"]
    if len(amounts) == 1:
        token = amounts[0]
        if token.value is not None and re.fullmatch(r"[ \t]*PLN[ \t|]*", following[token.end:], re.I):
            yield 1, 3, token


def order_numbers(rows):
    """Read the compact summary of a completed order with a wrapped date."""
    text = "\n".join(rows)
    if not COMPLETED_ORDER.search(text) or PENDING_ORDER.search(text):
        return
    for i in range(len(rows) - 3):
        heading, amount_line, mode, date_line = rows[i:i + 4]
        if not (ORDER_DETAILS.fullmatch(heading) and ORDER_MODE.match(mode)):
            continue
        date = ORDER_EXECUTION.search(date_line)
        if date is None or NON_EXECUTED_DATE.search(date_line[:date.start()]):
            continue
        if value := normalize(date["date"], "date"):
            yield i + 3, 3, Number("data_operacji", value, *date.span("date"))
            amount = MONEY_TOKEN.search(amount_line)
            if (amount and re.fullmatch(r"[\W_]{0,6}(?:kwota[ \t:]+)?", amount_line[:amount.start()], re.I)
                    and re.fullmatch(r"[ \t]*PLN[ \t|]*", amount_line[amount.end():], re.I)):
                if (value := money_value(amount[0])) is not None:
                    yield i + 1, 3, Number("kwota", value, *amount.span())


def labelled_numbers(rows):
    for i, (line, following) in enumerate(zip(rows, rows[1:])):
        for row, priority, token in structured_numbers(line, following):
            yield i + row, priority, token
    yield from order_numbers(rows)


def booking_value(line, following, after, previous):
    """A wrapped booking cell inside a bounded operation row with both roles."""
    if (not BOOKING_ROW.match(line) or LABELS.search(following)
            or any(token.key == "data_operacji" for token in number_tokens(line))):
        return None
    if not (date := BOOKING_VALUE.fullmatch(following)):
        return None
    operation = next((index for index, row in reversed(list(enumerate(previous)))
                      if EXECUTION_ROW.match(row)), None)
    if operation is None or not any(re.search(r"\bz rachunku\b", row, re.I) for row in previous[operation:]):
        return None
    if not (re.search(r"\bna rachunek\b", following, re.I)
            or re.match(r"^na rachunek\b", after, re.I)):
        return None
    return normalize(date["date"], "date")


def view_evidence(rows):
    candidates = defaultdict(list)
    for _, priority, token in labelled_numbers(rows):
        candidates[token.key].append((priority, token.value))
    for i, line in enumerate(rows):
        labels = list(LABELS.finditer(line))
        following = rows[i + 1] if i + 1 < len(rows) else ""
        after = rows[i + 2] if i + 2 < len(rows) else ""
        if value := booking_value(line, following, after, rows[max(0, i - 5):i]):
            candidates["data_operacji"].append((2, value))
        for j, label in enumerate(labels):
            key, priority = COLUMN[label.lastgroup]
            if not priority:
                continue
            end = labels[j + 1].start() if j + 1 < len(labels) else len(line)
            cell = line[label.end():end]
            if len(labels) == 1 and LABEL_GAP.fullmatch(cell) and not LABELS.search(following):
                cell = following
            values = {token.value for token in number_tokens(cell) if token.key == key and token.value is not None}
            if len(values) == 1:
                candidates[key].append((priority, values.pop()))
        if not labels and i and not any(not COLUMN[label.lastgroup][1] for label in LABELS.finditer(rows[i - 1])):
            # Broken headings can still leave an isolated amount and date row.
            tokens = number_tokens(line)
            if (len(tokens) == 2 and {token.key for token in tokens} == {"kwota", "data_operacji"}
                    and all(token.value is not None for token in tokens) and numeric_row(line, tokens)):
                for token in tokens:
                    candidates[token.key].append((1, token.value))
    return candidates


def token_value(token, key):
    # A cropped date must contain the complete numeric day, month and year.
    if key == "data_operacji":
        if re.fullmatch(r"[0-9./-]+", token) and DATE_TOKEN.fullmatch(token):
            return normalize(token, "date")
    elif MONEY_TOKEN.fullmatch(token):
        return money_value(token)
    return None


def numeric_boxes(tsv, rows, missing):
    evidence = view_evidence(rows)
    boxes = []
    for key in missing:
        hits = evidence.get(key, [])
        if not hits:
            continue
        rank = max(priority for priority, _ in hits)
        values = {value for priority, value in hits if priority == rank}
        if rank < 2 or len(values) != 1:
            continue
        value = values.pop()
        matches = []
        for line in tsv.splitlines():
            word = line.split("\t", 11)
            if len(word) == 12 and word[0] == "5" and token_value(word[11].strip(), key) == value:
                matches.append(tuple(map(int, word[6:10])))
        if len(matches) == 1:
            boxes.append((key, value, matches[0]))
    return boxes


def recovered_numbers(views):
    combined = defaultdict(list)
    checked = {(key, value, v.page) for v in views for key, value in v.verified}
    for profile, view in enumerate(views):
        for key, hits in view_evidence(view.rows).items():
            for priority, value in hits:
                combined[key].append((priority, value, view.page, profile))
    results = {}
    for key, entries in combined.items():
        rank = max(entry[0] for entry in entries)
        strongest = {(value, page) for priority, value, page, _ in entries if priority == rank}
        if len(strongest) != 1:
            continue
        value, page = strongest.pop()
        support = {profile for _, observed, source, profile in entries if (observed, source) == (value, page)}
        if len(support) >= 2 or (key, value, page) in checked:
            results[key] = value, page
    return results
