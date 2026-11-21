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


def table_numbers(header, values):
    """Bind a complete numeric row to its recognised column headers."""
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


def view_evidence(rows):
    candidates = defaultdict(list)
    for i, line in enumerate(rows):
        labels = list(LABELS.finditer(line))
        following = rows[i + 1] if i + 1 < len(rows) else ""
        for priority, token in table_numbers(line, following):
            candidates[token.key].append((priority, token.value))
        for j, label in enumerate(labels):
            key, priority = COLUMN[label.lastgroup]
            if not priority:
                continue
            end = labels[j + 1].start() if j + 1 < len(labels) else len(line)
            cell = line[label.end():end]
            if len(labels) == 1 and SEPARATORS.fullmatch(cell) and not LABELS.search(following):
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
