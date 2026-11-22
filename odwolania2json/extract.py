"""Odczyt PDF i przetwarzanie zgodnie z definicjami klas."""
import re
import unicodedata
from dataclasses import replace
from functools import partial

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .bank_accounts import (LABEL, PAYEE, PAYER, account_observations, apply_accounts,
                            explicit_account_conflicts, fold)
from .bank_scan import primary_scan_view, recovered_numbers, row_text
from .legal import BUILDERS as LEGAL_BUILDERS
from .model import Document, Extraction, FLAGS, classify, cover_limit, excluded_heading, schema_errors
from .ocr import LocalOCR
from .operations import apply_fields
from .podpisy import read_signature_guides
from .transfer import primary_number_fallback, transfer
from .transfer_cover import completed_transfer, neutral_cover
from .transfer_reference import apply_scan_reference
from .transfer_title import TITLE, apply_scan_title

BUILDERS = {**LEGAL_BUILDERS, "transfer": transfer}
DEFAULT_OCR_PAGE_BUDGET = 6
PAGE_READ_ERRORS = (PyPdfError, OSError, ValueError, RuntimeError, LookupError, TypeError, OverflowError)


class ReadError(ValueError):
    """PDF nie zawiera czytelnych stron."""


def clean_page(text):
    text = unicodedata.normalize("NFC", text).replace("\u00ad", "").replace("\u200b", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[^\S\n]+", " ", text)


def readable(text):
    return bool(re.search(r"[^\W\d_]{3}", text))


def plain_cover(page):
    """Reject mixed or graphical content hidden behind a native cover label."""
    resources = page.get("/Resources")
    resources = resources.get_object() if resources is not None else {}
    if not isinstance(resources, dict) or page.get("/Annots") or resources.get("/XObject"):
        return False
    content = page.get_contents()
    paint = {b"Do", b"INLINE IMAGE", b"sh", b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"}
    return content is not None and not any(operator in paint for _, operator in content.operations)


def read_pdf(path, ocr=None, max_pages=None, *, classes=None, ocr_page_budget=DEFAULT_OCR_PAGE_BUDGET):
    """Read all native text by default. Only distinct pages attempted by OCR spend its budget."""
    if type(ocr_page_budget) is not int or ocr_page_budget < 0:
        raise ValueError("Budżet OCR musi być nieujemną liczbą całkowitą.")
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
            selected = reader.pages if max_pages is None else reader.pages[:max_pages]
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
                except PAGE_READ_ERRORS:
                    observations[index] = observation(index + 1, "unassessed", "native_read_failed")
                    if max_pages is not None:
                        raise
                    # A damaged attachment must not remove evidence from other pages.
                    pages.append("")
                    continue
                pages.append(text)
                observations[index] = native_observation(index + 1, text, readable(text), skipped)

            transfer_cover_verified = False
            if count == len(pages) == 2 and neutral_cover(pages[0]):
                try:
                    transfer_cover_verified = plain_cover(selected[0])
                except PAGE_READ_ERRORS:
                    pass

        ocr_pages, orientations = [], []
        scanned_indices = set()
        single_page_layout = None
        scanner = ocr.oriented_pages if isinstance(ocr, LocalOCR) else ocr
        if isinstance(ocr, LocalOCR) and count == 1:
            scanner = partial(scanner, capture_layout=True)

        def read_scan(stop, *, start=None):
            nonlocal single_page_layout
            first = 0 if start is None else start
            allowed_stop = min(stop, first + ocr_page_budget - len(scanned_indices))
            for index in range(allowed_stop, stop):
                observations[index] = without_ocr_result(observations[index], "ocr_page_budget")
            if allowed_stop <= first:
                return
            stop = allowed_stop
            pending = set(range(first, stop))
            scanned_indices.update(pending)
            missing_reason = "ocr_no_page_result"
            try:
                results = scanner(path, stop) if start is None else scanner(path, stop, start=start)
                for index, text, *angle in results:
                    if index not in pending:
                        continue
                    pending.remove(index)
                    usable = readable(text)
                    if 0 <= index < len(pages):
                        observations[index] = ocr_observation(observations[index], text, usable)
                    if usable:
                        pages[index] = clean_page(text)
                        ocr_pages.append(index + 1)
                        if angle:
                            orientations.append((index, angle[0]))
                            if isinstance(ocr, LocalOCR) and count == 1 and len(angle) == 2:
                                single_page_layout = angle[1]
            except PAGE_READ_ERRORS:
                missing_reason = "ocr_interrupted"
                # Opening-page OCR and explicitly bounded reads retain their error contract.
                if start is None or max_pages is not None or not any(map(readable, pages)):
                    raise
            finally:
                for index in pending:
                    observations[index] = without_ocr_result(observations[index], missing_reason)

        read_error = "ocr_failed"
        attempted = 0
        if ocr and pages and not readable(pages[0]):
            # A later native appendix must not suppress OCR of the opening used for classification.
            attempted = 1 if any(map(readable, pages[:2])) else min(2, len(pages))
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
        transfer_config = classes.get("przelew", {}) if classes else {}
        if ocr and count == len(pages) == 2 and transfer_config.get("builder") == "transfer":
            if transfer_cover_verified and not readable(pages[1]) and 1 not in scanned_indices:
                if classify(Document.from_pages(pages), classes)[0] == "negative":
                    read_scan(2, start=1)
            elif isinstance(ocr, LocalOCR) and observations[0]["reason"] == "ocr_no_text":
                candidate = Document.from_pages(pages)
                if completed_transfer(candidate, transfer_config) and classify(candidate, classes)[0] == "negative":
                    try:
                        transfer_cover_verified = ocr.blank_opening(path)
                    except PAGE_READ_ERRORS:
                        pass
        if not any(map(readable, pages)):
            read_error = "no_readable_content"
            raise ReadError("brak czytelnej treści")
    except Exception as exc:
        exc.scan_quality = quality_report(observations, read_error)
        raise

    document = replace(Document.from_pages(pages), scan_quality=quality_report(observations),
                       ocr_layout_tsv=single_page_layout, transfer_cover_verified=transfer_cover_verified)
    if orientations:
        document = replace(document, bank_scan=partial(ocr.transfer_views, path, tuple(orientations)))
    if single_page_layout and orientations:
        document = replace(document, signature_guides=partial(
            read_signature_guides, ocr.document_type, path, orientations[0][1]
        ))
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
                # The primary TSV belongs to the replaced reading, while page
                # quality and the callable describe the original physical PDF.
                selected = replace(document, text=alternative.text, starts=alternative.starts,
                                   ocr_layout_tsv=None)
                return selected, name, signals
    return document, "negative", []


def transfer_page_views(scan):
    return [view for view in scan() if view.page == 2]


def extract(document, classes, *, capture_decision=False):
    primary = document
    name, signals = classify(document, classes)
    scan = document.bank_scan
    views = None
    if name == "negative" and scan and "przelew" in classes and possible_transfer_scan(document, classes["przelew"]):
        views = scan()
        document, name, signals = transfer_from_alternate_page(document, classes, views)
    cover_receipt = False
    if name == "negative" and document.transfer_cover_verified:
        candidate = completed_transfer(document, classes.get("przelew", {}))
        if candidate:
            _, name, signals = candidate
            cover_receipt = True
            offset = document.starts[1][0] - 3
            # Preserve the original physical offsets while giving field readers only the receipt.
            document = replace(document, text=" " * offset + document.text[offset:],
                               bank_scan=partial(transfer_page_views, scan) if scan else None)
            views = None
    if name == "negative":
        return None, {"class": name, "status": "negative", "signals": signals, "fields": {}}
    return extract_class(document, classes, name, signals, views=views, capture_decision=capture_decision,
                         primary_document=primary, cover_receipt=cover_receipt)


def extract_class(document, classes, name, signals, *, views=None, capture_decision=False,
                  primary_document=None, cover_receipt=False):
    """Extract fields of an identified class, preserving the normal local field rules."""
    config = classes[name]
    result = Extraction(document, config["schema"], signals)
    apply_fields(result, config.get("fields", {}), document.text)
    builder = config.get("builder")
    if capture_decision and builder == "appeal":
        details = BUILDERS[builder](result, config, capture_decision=True)
    else:
        details = BUILDERS[builder](result, config) if builder else {}
    if builder == "transfer":
        if views is not None:
            details["classification_from_ocr_layout"] = True
        apply_bank_scans(result, config, views, primary_document, cover_receipt=cover_receipt)
    errors = list(schema_errors(result.data, config["schema"]))
    if errors:
        raise ValueError(f"{name}: " + "; ".join(errors))
    return result.data, {"class": name, "status": "ok", "signals": signals,
                         "fields": result.evidence, **details}


def apply_bank_scans(result, config, views, primary_document, *, cover_receipt=False):
    """Give each bank field reader only the physical observations already available."""
    document = result.document
    primary_number_fallback(result, primary_document)
    bank = result.data["przelew_bankowy"]
    missing_numbers = any(bank[key] is None for key in ("kwota", "data_operacji"))
    if document.bank_scan and views is None and (missing_numbers or LABEL.search(fold(document.text))):
        views = document.bank_scan()
    scans = tuple(views or ())

    pages = document.text.split("\n\f\n")[:-1]
    evidence = [(page, account_observations(text.splitlines())) for page, text in enumerate(pages, 1)]
    for view in scans:
        rows = row_text(view.positions) if view.positions else view.rows
        evidence.append((view.page, account_observations(rows, view.positions)))
    apply_accounts(result, evidence, scanned={view.page for view in scans})
    if cover_receipt:
        conflicts = explicit_account_conflicts(pages[1].splitlines())
        for role in (PAYER, PAYEE):
            candidates = {number for _, reading in evidence for number in reading.get(role, ())}
            if role in conflicts or len(candidates) > 1:
                bank[role] = None
                result.evidence.pop("przelew_bankowy." + role, None)

    primary_view = primary_scan_view(primary_document or document)
    apply_scan_title(result, config["fields"].get(TITLE, ()), views=scans, primary_document=primary_document)
    reference_scans = (*scans, primary_view) if primary_view and document.ocr_layout_tsv is None else scans
    apply_scan_reference(result, reference_scans)

    if missing_numbers:
        numbers = recovered_numbers(scans)
        if primary_view and any(bank[key] is None and key not in numbers for key in ("kwota", "data_operacji")):
            # An independent primary read can corroborate an alternate view.
            # Values already supported by the alternate reads keep precedence.
            for key, reading in recovered_numbers((*scans, primary_view)).items():
                numbers.setdefault(key, reading)
        for key, (value, page) in numbers.items():
            if bank[key] is None:
                result.put(("przelew_bankowy", key), value, document.starts[page - 1][0],
                           "ocr_wiersz_kwoty" if key == "kwota" else "ocr_wiersz_daty")
