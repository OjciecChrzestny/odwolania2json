"""Odczyt PDF i przetwarzanie zgodnie z definicjami klas."""
import re
import unicodedata
from dataclasses import replace
from functools import partial

from pypdf import PdfReader

from .bank_accounts import LABEL, account_observations, apply_accounts, fold
from .bank_scan import recovered_numbers, row_text
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
    """Read the extraction text and attach scan quality to the document or raised error."""
    from .scan_quality import (native_observation, observation, ocr_observation,
                               quality_report, without_ocr_result)

    observations = None
    read_error = "pdf_open_failed"
    try:
        with path.open("rb") as stream:
            reader = PdfReader(stream)
            if reader.is_encrypted and not reader.decrypt(""):
                read_error = "pdf_encrypted"
                raise ReadError("PDF jest zaszyfrowany")
            read_error = "pdf_page_tree_failed"
            selected = reader.pages[:max_pages]
            count = len(reader.pages)
            limit = len(selected)
            observations = [observation(number, "unassessed",
                                        "native_read_aborted" if number <= limit else "page_limit")
                            for number in range(1, count + 1)]
            pages = []
            skipped = "ocr_not_selected" if ocr else "ocr_not_configured"
            read_error = "native_read_failed"
            for index in range(limit):
                try:
                    text = clean_page(selected[index].extract_text() or "")
                except Exception:
                    observations[index] = observation(index + 1, "unassessed", "native_read_failed")
                    raise
                pages.append(text)
                observations[index] = native_observation(index + 1, text, readable(text), skipped)

        ocr_pages, orientations = [], []
        scanned_indices = set()
        scanner = ocr.oriented_pages if isinstance(ocr, LocalOCR) else ocr

        def read_scan(stop, *, start=None):
            first = 0 if start is None else start
            pending = set(range(first, stop))
            scanned_indices.update(pending)
            missing_reason = "ocr_no_page_result"
            try:
                results = scanner(path, stop) if start is None else scanner(path, stop, start=start)
                for index, text, *angle in results:
                    pending.discard(index)
                    usable = readable(text)
                    if 0 <= index < len(pages):
                        observations[index] = ocr_observation(observations[index], text, usable)
                    if usable:
                        pages[index] = clean_page(text)
                        ocr_pages.append(index + 1)
                        if angle:
                            orientations.append((index, angle[0]))
            except Exception:
                missing_reason = "ocr_interrupted"
                raise
            finally:
                for index in pending:
                    observations[index] = without_ocr_result(observations[index], missing_reason)

        read_error = "ocr_failed"
        attempted = 0
        if ocr and pages and not readable(pages[0]):
            attempted = 1 if any(map(readable, pages)) else min(2, len(pages))
            read_scan(attempted)
        if ocr and classes and pages:
            limit = max((cover_limit(pages[0], config) for config in classes.values()), default=0)
            missing = [i for i in range(max(1, attempted), min(limit, len(pages))) if not readable(pages[i])]
            if missing and classify(Document.from_pages(pages), classes)[0] == "negative":
                for i in missing:
                    read_scan(i + 1, start=i)
            remaining = [i for i, text in enumerate(pages) if i not in scanned_indices and not readable(text)]
            if remaining:
                name, _ = classify(Document.from_pages(pages), classes)
                if classes.get(name, {}).get("builder") == "appeal":
                    for i in remaining:
                        read_scan(i + 1, start=i)
        if not any(map(readable, pages)):
            read_error = "no_readable_content"
            raise ReadError("brak czytelnej treści")
    except Exception as exc:
        exc.scan_quality = quality_report(observations, read_error)
        raise

    document = replace(Document.from_pages(pages), scan_quality=quality_report(observations))
    if orientations:
        document = replace(document, bank_scan=partial(ocr.transfer_views, path, tuple(orientations)))
    return document, ocr_pages


def possible_transfer_scan(document, config):
    first = document.text.split("\f", 1)[0]
    if excluded_heading(first, config) or (config.get("exclude_page") and re.search(config["exclude_page"], first, FLAGS)):
        return False
    if any(signal.get("retry_ocr") and re.search(signal["pattern"], first[:600], FLAGS)
           for signal in config["signals"]):
        return True
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
    if builder == "transfer":
        bank = result.data["przelew_bankowy"]
        pages = document.text.split("\n\x0c\n")[:-1]
        evidence = [(i, account_observations(page.splitlines())) for i, page in enumerate(pages, 1)]
        if views is not None:
            details["classification_from_ocr_layout"] = True
        missing_number = any(bank[key] is None for key in ("kwota", "data_operacji"))
        if scan and views is None and (missing_number or LABEL.search(fold(document.text))):
            views = scan()
        for view in views or ():
            rows = row_text(view.positions) if view.positions else view.rows
            evidence.append((view.page, account_observations(rows, view.positions)))
        apply_accounts(result, evidence, scanned={view.page for view in views or ()})
        if missing_number:
            for key, (value, page) in recovered_numbers(views or ()).items():
                if bank[key] is None:
                    result.put(("przelew_bankowy", key), value, document.starts[page - 1][0],
                               "ocr_wiersz_kwoty" if key == "kwota" else "ocr_wiersz_daty")
    errors = list(schema_errors(result.data, config["schema"]))
    if errors:
        raise ValueError(f"{name}: " + "; ".join(errors))
    return result.data, {"class": name, "status": "ok", "signals": signals,
                         "fields": result.evidence, **details}
