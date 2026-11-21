"""Odczyt PDF i przetwarzanie zgodnie z definicjami klas."""
import re
import unicodedata
from dataclasses import replace
from functools import partial

from pypdf import PdfReader

from .bank_scan import recovered_numbers
from .legal import BUILDERS as LEGAL_BUILDERS
from .model import Document, Extraction, FLAGS, classify, cover_limit, excluded_heading, schema_errors
from .ocr import LocalOCR
from .operations import apply_fields
from .transfer import transfer

BUILDERS = {**LEGAL_BUILDERS, "transfer": transfer}


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
    ocr_pages, orientations = [], []
    scanner = ocr.oriented_pages if isinstance(ocr, LocalOCR) else ocr
    def read_scan(results):
        for index, text, *angle in results:
            if readable(text):
                pages[index] = clean_page(text)
                ocr_pages.append(index + 1)
                if angle:
                    orientations.append((index, angle[0]))

    attempted = 0
    if ocr and pages and not readable(pages[0]):
        attempted = 1 if any(map(readable, pages)) else min(2, len(pages))
        read_scan(scanner(path, attempted))
    if ocr and classes and pages:
        limit = max((cover_limit(pages[0], config) for config in classes.values()), default=0)
        missing = [i for i in range(max(1, attempted), min(limit, len(pages))) if not readable(pages[i])]
        if missing and classify(Document.from_pages(pages), classes)[0] == "negative":
            for i in missing:
                read_scan(scanner(path, i + 1, start=i))
    if not any(map(readable, pages)):
        raise ReadError("brak czytelnej treści")
    document = Document.from_pages(pages)
    if orientations:
        document = replace(document, bank_scan=partial(ocr.transfer_views, path, tuple(orientations)))
    return document, ocr_pages


def possible_transfer_scan(document, config):
    first = document.text.split("\f", 1)[0]
    if excluded_heading(first, config) or (config.get("exclude_page") and re.search(config["exclude_page"], first, FLAGS)):
        return False
    return (re.search(r"\bprzelew\w*", first[:600], FLAGS) is not None
            and re.search(r"\b(?:polecenie|rachun\w*|nadawc\w*|bank)\b", first[:1400], FLAGS) is not None)


def transfer_from_alternate_page(document, classes, views):
    pages = document.text.split("\n\f\n")[:-1]
    for view in views:
        if view.page != 1:
            continue
        for reading in (view.text, "\n".join(view.rows)):
            alternative = Document.from_pages([clean_page(reading), *pages[1:]])
            name, signals = classify(alternative, classes)
            if name == "przelew":
                return alternative, name, signals
    return document, "negative", []


def extract(document, classes, *, capture_decision=False):
    name, signals = classify(document, classes)
    scan = document.bank_scan
    views = None
    if name == "negative" and scan and "przelew" in classes and possible_transfer_scan(document, classes["przelew"]):
        views = scan()
        document, name, signals = transfer_from_alternate_page(document, classes, views)
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
    if builder == "transfer" and scan:
        bank = result.data["przelew_bankowy"]
        if views is not None:
            details["classification_from_ocr_layout"] = True
        if any(bank[key] is None for key in ("kwota", "data_operacji")):
            for key, (value, page) in recovered_numbers(views if views is not None else scan()).items():
                if bank[key] is None:
                    result.put(("przelew_bankowy", key), value, document.starts[page - 1][0],
                               "ocr_wiersz_kwoty" if key == "kwota" else "ocr_wiersz_daty")
    errors = list(schema_errors(result.data, config["schema"]))
    if errors:
        raise ValueError(f"{name}: " + "; ".join(errors))
    return result.data, {"class": name, "status": "ok", "signals": signals,
                         "fields": result.evidence, **details}
