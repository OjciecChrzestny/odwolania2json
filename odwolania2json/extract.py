"""Odczyt PDF i przetwarzanie zgodnie z definicjami klas."""
import re
import unicodedata

from pypdf import PdfReader

from .legal import BUILDERS
from .model import Document, Extraction, classify, cover_limit, schema_errors
from .operations import apply_fields


class ReadError(ValueError):
    """PDF nie zawiera czytelnych stron."""


def clean_page(text):
    text = unicodedata.normalize("NFC", text).replace("\u00ad", "").replace("\u200b", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[^\S\n]+", " ", text)


def readable(text):
    return bool(re.search(r"[^\W\d_]{3}", text))


def read_pdf(path, ocr=None, max_pages=6, *, classes=None):
    with path.open("rb") as stream:
        reader = PdfReader(stream)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ReadError("PDF jest zaszyfrowany")
        pages = [clean_page(page.extract_text() or "") for page in reader.pages[:max_pages]]
    ocr_pages = []
    def read_scan(results):
        for index, text in results:
            if readable(text):
                pages[index] = clean_page(text)
                ocr_pages.append(index + 1)

    attempted = 0
    if ocr and pages and not readable(pages[0]):
        attempted = 1 if any(map(readable, pages)) else min(2, len(pages))
        read_scan(ocr(path, attempted))
    if ocr and classes and pages:
        limit = max((cover_limit(pages[0], config) for config in classes.values()), default=0)
        missing = [i for i in range(max(1, attempted), min(limit, len(pages))) if not readable(pages[i])]
        if missing and classify(Document.from_pages(pages), classes)[0] == "negative":
            for i in missing:
                read_scan(ocr(path, i + 1, start=i))
    if not any(map(readable, pages)):
        raise ReadError("brak czytelnej treści")
    return Document.from_pages(pages), ocr_pages


def extract(document, classes, *, capture_decision=False):
    name, signals = classify(document, classes)
    if name == "negative":
        return None, {"class": name, "status": "negative", "signals": signals, "fields": {}}
    config = classes[name]
    result = Extraction(document, config["schema"], signals)
    apply_fields(result, config.get("fields", {}), document.text)
    builder = config.get("builder")
    if capture_decision and builder == "appeal":
        details = BUILDERS[builder](result, config, capture_decision=True)
    else:
        details = BUILDERS[builder](result, config) if builder else {}
    errors = list(schema_errors(result.data, config["schema"]))
    if errors:
        raise ValueError(f"{name}: " + "; ".join(errors))
    return result.data, {"class": name, "status": "ok", "signals": signals,
                         "fields": result.evidence, **details}
