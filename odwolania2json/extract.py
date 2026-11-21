"""Odczyt PDF i przetwarzanie zgodnie z definicjami klas."""
import re
import unicodedata

from pypdf import PdfReader

from .legal import BUILDERS
from .model import Document, Extraction, classify, schema_errors
from .operations import apply_fields


class ReadError(ValueError):
    """PDF nie zawiera czytelnych stron."""


def clean_page(text):
    text = unicodedata.normalize("NFC", text).replace("\u00ad", "").replace("\u200b", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[^\S\n]+", " ", text)


def readable(text):
    return bool(re.search(r"[^\W\d_]{3}", text))


def read_pdf(path, ocr=None, max_pages=6):
    with path.open("rb") as stream:
        reader = PdfReader(stream)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ReadError("PDF jest zaszyfrowany")
        pages = [clean_page(page.extract_text() or "") for page in reader.pages[:max_pages]]
    ocr_pages = []
    if ocr and pages and not readable(pages[0]):
        for index, text in ocr(path, 1 if any(map(readable, pages)) else min(2, len(pages))):
            if readable(text):
                pages[index] = clean_page(text)
                ocr_pages.append(index + 1)
    if not any(map(readable, pages)):
        raise ReadError("brak czytelnej treści")
    return Document.from_pages(pages), ocr_pages


def extract(document, classes):
    name, signals = classify(document, classes)
    if name == "negative":
        return None, {"class": name, "status": "negative", "signals": signals, "fields": {}}
    config = classes[name]
    result = Extraction(document, config["schema"])
    apply_fields(result, config.get("fields", {}), document.text)
    builder = config.get("builder")
    details = BUILDERS[builder](result, config) if builder else {}
    errors = list(schema_errors(result.data, config["schema"]))
    if errors:
        raise ValueError(f"{name}: " + "; ".join(errors))
    return result.data, {"class": name, "status": "ok", "signals": signals,
                         "fields": result.evidence, **details}
