"""Wspólny kontrakt klas i zapis pochodzenia pól."""
import json
import math
import re
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from collections.abc import Callable

DEFAULT_CONFIG = Path(__file__).with_name("classes")
FLAGS = re.IGNORECASE | re.MULTILINE


@dataclass(frozen=True)
class Document:
    text: str
    starts: tuple
    bank_scan: Callable | None = field(default=None, repr=False, compare=False)
    scan_quality: dict | None = field(default=None, repr=False, compare=False)
    ocr_layout_tsv: str | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_pages(cls, pages):
        starts, parts = [], []
        offset = 0
        for number, page in enumerate(pages, 1):
            starts.append((offset, number))
            parts.extend((page, "\n\f\n"))
            offset += len(page) + 3
        return cls("".join(parts), tuple(starts))

    def page(self, offset):
        index = bisect_right(self.starts, (offset, float("inf"))) - 1
        return self.starts[index][1]


def load_classes(root=DEFAULT_CONFIG):
    classes = {}
    for path in sorted(root.glob("*.json")):
        config = json.loads(path.read_text(encoding="utf-8"))
        name = config["class"]
        if name in classes or name in {"negative", "read_error"}:
            raise ValueError(f"{path}: niedozwolona lub powtórzona klasa {name}")
        for signal in config["signals"]:
            re.compile(signal["pattern"], FLAGS)
            for pattern in signal.get("requires", {}).values():
                re.compile(pattern, FLAGS)
        for rules in config.get("fields", {}).values():
            for rule in rules:
                re.compile(rule["pattern"], FLAGS)
        classes[name] = config
    if not classes:
        raise ValueError(f"{root}: brak konfiguracji klas")
    return classes


def excluded_heading(text, config):
    pattern = config.get("exclude_heading")
    return pattern and re.search(pattern, text[:400], FLAGS)


def cover_limit(first_page, config):
    policy = config.get("cover_continuation")
    if policy and not excluded_heading(first_page, config) and re.search(policy["cover"], first_page, FLAGS):
        return policy["through_page"]
    return 0


def signal_offset(signal, text):
    required = signal.get("requires")
    if not required:
        match = re.search(signal["pattern"], text, FLAGS)
        return match.start() if match else None

    # A title and its supporting fields must belong to one physical page.
    start = 0
    for page in text.split("\f"):
        match = re.search(signal["pattern"], page, FLAGS)
        if match and all(re.search(pattern, page, FLAGS) for pattern in required.values()):
            return start + match.start()
        start += len(page) + 1
    return None


def class_candidate(document, name, config, text, offset=0, required=()):
    if excluded_heading(text, config) or (config.get("exclude_page") and re.search(config["exclude_page"], text, FLAGS)):
        return None
    score = 0
    evidence = []
    for signal in config["signals"]:
        position = signal_offset(signal, text)
        if position is not None:
            score += signal["weight"]
            entry = {"rule": signal["name"], "page": document.page(offset + position)}
            if "requires" in signal:
                entry["criteria"] = list(signal["requires"])
            evidence.append(entry)
    if score >= config["threshold"] and set(required).issubset(item["rule"] for item in evidence):
        return score, name, evidence
    return None


def classify(document, classes):
    pages = document.text.split("\f")
    candidates = []
    for name, config in classes.items():
        opening = "\f".join(pages[:config.get("classification_pages", 2)])
        candidate = class_candidate(document, name, config, opening)
        if candidate:
            candidates.append(candidate)

    # Pismo przewodnie wymaga niezależnych sygnałów na tej samej dalszej stronie.
    if not candidates:
        for name, config in classes.items():
            limit = cover_limit(pages[0], config)
            for start, number in document.starts[1:limit]:
                end = document.starts[number][0] if number < len(document.starts) else len(document.text)
                candidate = class_candidate(document, name, config, document.text[start:end], start,
                                            config["cover_continuation"]["required_signals"])
                if candidate:
                    candidates.append(candidate)
                    break
    candidates.sort(key=lambda entry: (-entry[0], entry[1]))
    if not candidates or len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return "negative", []
    return candidates[0][1], candidates[0][2]


def empty(schema):
    if isinstance(schema, dict):
        return {key: empty(child) for key, child in schema.items()}
    if isinstance(schema, list):
        return []
    return None


def iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def schema_errors(value, schema, field="$"):
    if isinstance(schema, dict):
        if not isinstance(value, dict):
            yield f"{field}: oczekiwany obiekt"
            return
        for key in sorted(value.keys() - schema.keys()):
            yield f"{field}.{key}: nadmiarowy klucz"
        for key, child in schema.items():
            path = f"{field}.{key}"
            if key not in value:
                yield f"{path}: brak wymaganego klucza"
            else:
                yield from schema_errors(value[key], child, path)
    elif isinstance(schema, list):
        if not isinstance(value, list):
            yield f"{field}: oczekiwana lista"
            return
        for index, item in enumerate(value):
            yield from schema_errors(item, schema[0], f"{field}[{index}]")
    elif value is None and schema.endswith("?"):
        return
    else:
        check = {
            "text": lambda v: isinstance(v, str),
            "number": lambda v: type(v) is int or type(v) is float and math.isfinite(v),
            "date": iso_date,
            "integer": lambda v: type(v) is int,
            "flag": lambda v: type(v) is int and v in (0, 1),
            "reason": lambda v: type(v) is int and 1 <= v <= 12,
            "person_type": lambda v: v in ("osoba_fizyczna", "osoba_prawna"),
        }[schema.rstrip("?")]
        if not check(value):
            yield f"{field}: oczekiwany typ {schema}"


class Extraction:
    def __init__(self, document, schema, signals=()):
        self.document = document
        self.signals = signals
        self.data = empty(schema)
        self.evidence = {}

    def put(self, path, value, offset, rule, *, span_end=None, operation="text", source=None):
        if value is None:
            return
        from .field_evidence import record_field_evidence
        target = self.data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        field = ".".join(str(key) for key in path)
        self.evidence[field] = record_field_evidence(
            self.document, field, value, offset, rule,
            span_end=span_end, operation=operation, source=source,
        )
