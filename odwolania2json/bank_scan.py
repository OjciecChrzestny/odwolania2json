"""Recover payment amounts and dates from the visual rows of a bank scan."""
import re
from collections import defaultdict
from dataclasses import dataclass
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
    r"(?<![\d.,])[-−+]?(?:\d{1,3}(?:[ .]\d{3})+|\d+)[,.][ \t]*\d{2}(?![\d.,])"
)
AMOUNT_LABEL = re.compile(r"\b(?:kwota|wartość|wartosc|amount)\b", re.I)
DATE_LABEL = re.compile(r"\b(?:data (?:operacji|transakcji|realizacji|wykonania)|execution date|date of operation)\b", re.I)
BOOKING_LABEL = re.compile(r"\b(?:data ksi[ęe]gowania|booking date)\b", re.I)
OTHER = re.compile(r"\b(?:prowizj\w*|op[łl]at[ayę]|sald[oa]|kurs|wydruk\w*|wystawieni\w*|wygenerow\w*|utworzeni\w*|należności)\b", re.I)


def typed_values(line):
    """Parse only complete numbers and real calendar dates. Mask dates before parsing amounts."""
    dates = list(DATE_TOKEN.finditer(line))
    values = {"data_operacji": set(), "kwota": set()}
    for match in dates:
        value = normalize(match[0], "date")
        if value is not None:
            values["data_operacji"].add(value)
    rest = DATE_TOKEN.sub(" ", line)
    for match in MONEY_TOKEN.finditer(rest):
        value = normalize(match[0], "money")
        if value is not None:
            values["kwota"].add(abs(value))
    return values


def view_evidence(rows):
    candidates = defaultdict(list)
    for i, line in enumerate(rows):
        if OTHER.search(line):
            continue
        values = typed_values(line)
        for key, label, priority in (("kwota", AMOUNT_LABEL, 3), ("data_operacji", DATE_LABEL, 3),
                                     ("data_operacji", BOOKING_LABEL, 2)):
            if not label.search(line):
                continue
            hits = values[key]
            if not hits and i + 1 < len(rows):
                following = rows[i + 1]
                # A following labelled field starts its own row, regardless of spacing.
                if not any(p.search(following) for p in (OTHER, AMOUNT_LABEL, DATE_LABEL, BOOKING_LABEL)):
                    hits = typed_values(following)[key]
            if len(hits) == 1:
                candidates[key].append((priority, next(iter(hits))))
        if len(values["kwota"]) == len(values["data_operacji"]) == 1:
            # When the headings break during OCR the two types still identify a row
            # consisting solely of the transaction amount, currency and date.
            rest = MONEY_TOKEN.sub("", DATE_TOKEN.sub("", line))
            if re.fullmatch(r"(?:\s|PLN|zł|[|:;])*", rest, re.I) and i and not OTHER.search(rows[i - 1]):
                for key, hits in values.items():
                    candidates[key].append((1, next(iter(hits))))
    return candidates


def token_value(token, key):
    # A cropped date must contain the complete numeric day, month and year.
    if key == "data_operacji":
        if re.fullmatch(r"[0-9./-]+", token) and DATE_TOKEN.fullmatch(token):
            return normalize(token, "date")
    elif MONEY_TOKEN.fullmatch(token):
        return abs(normalize(token, "money"))
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
