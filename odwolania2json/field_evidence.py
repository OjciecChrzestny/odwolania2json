"""Evidence from the exact page reading used by the extractor.

Pages are numbered from 1. A span contains zero-based, half-open character
offsets in the cleaned page text used for extraction. These are not PDF
coordinates. A snippet is copied verbatim from that text, including OCR errors.
"""
import json
import re
from functools import cache

from .model import DEFAULT_CONFIG, FLAGS
from .operations import DATE, normalize

MAX_SNIPPET_LENGTH = 240
OCR_RECOVERY_RULES = {"ocr_wiersz_kwoty", "ocr_wiersz_daty"}


@cache
def _transfer_rules():
    """Reuse stock rules whose legacy caller records the start of capture 1."""
    config = json.loads((DEFAULT_CONFIG / "przelew.json").read_text(encoding="utf-8"))
    return {
        (path, rule["name"]): (
            re.compile(rule["pattern"].replace("<DATE>", DATE), FLAGS),
            rule.get("operation", "text"),
        )
        for path, rules in config["fields"].items()
        for rule in rules
    }


def _capture(page_text, start, path, rule, value):
    if not path.startswith("przelew_bankowy."):
        return None
    definition = _transfer_rules().get((path, rule))
    if definition is None:
        return None
    pattern, operation = definition
    for match in pattern.finditer(page_text):
        if match.start(1) == start and normalize(match[1], operation) == value:
            return match
    return None


def record_field_evidence(document, path, value, offset, rule, *,
                          span_end=None, operation="text", source=None):
    """Record a legacy page hint or validate a caller's explicit value span.

    A caller supplying span_end must use the same buffer as document.text.
    It supplies an absolute end offset and the value's normalization operation.
    A caller with only a page hint can leave span_end absent.
    """
    record = {"page": None, "rule": rule, "source": source, "precision": "unavailable"}
    if not document.starts or not document.starts[0][0] <= offset < len(document.text):
        return record

    page = document.page(offset)
    record.update(page=page, precision="page")
    if source is None and rule in OCR_RECOVERY_RULES:
        record["source"] = "ocr"

    page_start = document.starts[page - 1][0]
    page_end = document.starts[page][0] if page < len(document.starts) else len(document.text)
    start = offset - page_start
    page_text = document.text[page_start:page_end].removesuffix("\n\f\n")
    match = None
    if span_end is None:
        # Never locate a value by searching for it on a page. Require the
        # labelled capture at the precise offset selected by the rule.
        match = _capture(page_text, start, path, rule, value)
        end = match.end(1) if match else None
    else:
        end = span_end - page_start
        if not start < end <= len(page_text) or normalize(page_text[start:end], operation) != value:
            end = None
    if end is not None and start < end <= min(len(page_text), start + MAX_SNIPPET_LENGTH):
        snippet = page_text[start:end]
        if snippet.strip() and "\f" not in snippet:
            record.update(precision="snippet", snippet=snippet, span={"start": start, "end": end})
            if match and match.start() < start and page_text.count(snippet) > 1:
                context = page_text[match.start():end]
                if len(context) <= MAX_SNIPPET_LENGTH and "\f" not in context:
                    record["context"] = context
    return record


def with_field_sources(fields, *, ocr_pages):
    """Resolve input provenance using read_pdf's one-based OCR page numbers.

    Call on fields from the same document read. Keep explicit sources from
    rules that used another reading. An unlocated record can stay unresolved.
    """
    scanned = set(ocr_pages)
    resolved = {}
    for path, record in fields.items():
        page, source = record.get("page"), record.get("source")
        if source is None and page is not None:
            source = "ocr" if page in scanned else "text"
        resolved[path] = {**record, "source": source}
    return resolved
