"""Publiczny interfejs wiersza poleceń."""
import argparse
import json
import logging
import os
import sqlite3
import sys
from contextlib import closing, contextmanager
from functools import partial
from pathlib import Path
from tempfile import NamedTemporaryFile

from pypdf.errors import PyPdfError

from .appeal_procedure import read_pdf_with_title_evidence
from .extract import DEFAULT_OCR_PAGE_BUDGET
from .filing_reason import filing_extractor, source_clause
from .filing_subject import filing_subject_extractor
from .model import DEFAULT_CONFIG, load_classes
from .ocr import prepare_ocr
from .power_name_ocr import verify_power_name
from .review import (REPORT_VERSION, config_digest, digest, extractor_revision, journal_path,
                     pdf_digest, review_details, run_review)


_DEFAULT_EXTRACT_DOCUMENT = filing_subject_extractor(filing_extractor("rule"), source_clause)


def state_directory(output_dir):
    return output_dir.with_name(f".{output_dir.name}.odwolania2json")


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def target(root, name):
    path = root / name
    if path.resolve() != path or not path.is_relative_to(root) or path.suffix != ".json":
        raise ValueError(f"Niebezpieczna ścieżka wyniku {path}")
    return path


@contextmanager
def output_lock(output_dir):
    state = state_directory(output_dir)
    if state.is_symlink():
        raise ValueError(f"Ewidencja wyników jest dowiązaniem symbolicznym: {state}")
    state.mkdir(exist_ok=True)
    journal, lock_file = state / "owned", state / "lock"
    if journal.is_symlink() or lock_file.is_symlink():
        raise ValueError(f"Plik ewidencji wyników jest dowiązaniem symbolicznym: {state}")
    with closing(sqlite3.connect(lock_file, timeout=30)) as lock:
        lock.execute("BEGIN IMMEDIATE")
        yield journal


def process(input_dir, output_dir, classes, diagnostics, ocr=None, *,
            read_document=None, extract_document=_DEFAULT_EXTRACT_DOCUMENT, ocr_page_budget=DEFAULT_OCR_PAGE_BUDGET,
            negative_verifier=None):
    if read_document is None:
        read_document = partial(read_pdf_with_title_evidence, ocr_page_budget=ocr_page_budget)
    input_dir.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(path for path in input_dir.rglob("*")
                  if path.suffix.lower() == ".pdf" and path.is_file())
    sources = {p.relative_to(input_dir).with_suffix(".json").as_posix(): p for p in pdfs}
    if len({os.path.normcase(name) for name in sources}) != len(pdfs):
        raise ValueError("Kilka wejściowych PDF-ów wskazuje ten sam wynik")

    output_dir.mkdir(parents=True, exist_ok=True)
    config_sha256 = config_digest(classes)
    ocr_enabled = ocr is not None
    revision = extractor_revision(config_sha256, ocr_enabled, ocr_page_budget=ocr_page_budget,
                                  verifier_profile=negative_verifier.profile if negative_verifier else None)
    with output_lock(output_dir) as journal:
        owned = set(json.loads(journal.read_text(encoding="utf-8"))) if journal.exists() else set()
        for name in owned | sources.keys():
            path = target(output_dir, name)
            if path.exists() and (name not in owned or not path.is_file()):
                raise ValueError(f"Istniejący plik poza ewidencją wyników {path}")
        # Rezerwacja przed zapisaniem wyników pozwala wznowić przerwany przebieg.
        write_file(journal, json_bytes(sorted(owned | sources.keys())))
        current, records = set(), []
        for name, pdf in sorted(sources.items()):
            pdf_sha256 = None
            document, value, read_error_quality = None, None, None
            try:
                pdf_sha256 = pdf_digest(pdf)
                document, ocr_pages = read_document(pdf, ocr, classes=classes)
            except (OSError, ValueError, PyPdfError, KeyError, TypeError, RuntimeError, IndexError, OverflowError) as exc:
                logging.error("%r — błąd odczytu (%s)", name, type(exc).__name__)
                read_error_quality = getattr(exc, "scan_quality", None)
                record = {"class": "read_error", "status": "read_error",
                          "error": str(exc), "fields": {}}
            else:
                value, record = extract_document(document, classes)
                if classes.get(record["class"], {}).get("builder") == "power_of_attorney":
                    value, record = verify_power_name(pdf, ocr, value, record, ocr_pages)
                record = {**record, "ocr_pages": ocr_pages}
                if negative_verifier is not None and record["status"] == "negative" and "przelew" in classes:
                    value, record = negative_verifier(pdf, document, classes, record)

            output_sha256 = None
            if record["status"] != "read_error":
                try:
                    if pdf_digest(pdf) != pdf_sha256:
                        raise ValueError("PDF zmienił się podczas ekstrakcji.")
                except (OSError, ValueError) as exc:
                    logging.error("%r — wejście zmienione podczas ekstrakcji", name)
                    document, value = None, None
                    record = {"class": "read_error", "status": "read_error",
                              "error": str(exc), "fields": {}}
                else:
                    content = b"" if value is None else json_bytes(value)
                    write_file(target(output_dir, name), content)
                    output_sha256 = digest(content)
                    current.add(name)
            details = review_details(document, record, value, ocr_enabled,
                                     read_error_quality=read_error_quality)
            records.append({"output": name, **record, **details,
                            "report_version": REPORT_VERSION,
                            "input": pdf.relative_to(input_dir).as_posix(), "pdf_sha256": pdf_sha256,
                            "output_sha256": output_sha256, "extractor_revision": revision,
                            "config_sha256": config_sha256})
        for name in (owned | sources.keys()) - current:
            target(output_dir, name).unlink(missing_ok=True)
        write_file(journal, json_bytes(sorted(current)))
        write_file(diagnostics, json_bytes({"documents": records}))
    failed = len(pdfs) - len(current)
    print(f"PDF: {len(pdfs)}. Wyniki: {len(current)}. Błędy odczytu: {failed}.")
    return 1 if failed else 0


def overlaps(first, second):
    return first.is_relative_to(second) or second.is_relative_to(first)


def main():
    parser = argparse.ArgumentParser(description="Lokalna ekstrakcja danych z PDF-ów UZP.")
    parser.add_argument("--input", type=Path, default=Path("input"), help="katalog PDF-ów")
    parser.add_argument("--output", type=Path, default=Path("output"), help="katalog wyników JSON")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="katalog konfiguracji klas")
    parser.add_argument("--diagnostics", type=Path, default=Path("diagnostics/last-run.json"),
                        help="plik diagnostyki poza wejściem i wyjściem")
    parser.add_argument("--ocr-max-pages", type=int, default=DEFAULT_OCR_PAGE_BUDGET,
                        help="maksymalna liczba różnych stron poddanych OCR na PDF (domyślnie 6)")
    parser.add_argument("--ocr-data", type=Path, help="katalog pol.traineddata dla opcjonalnego OCR")
    commands = parser.add_subparsers(dest="command")
    review = commands.add_parser("review", help="kolejka operatora i lokalny dziennik decyzji")
    actions = review.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="wyświetl dokumenty oczekujące na kontrolę")
    show = actions.add_parser("show", help="wyświetl wynik, strony, dowody i decyzję")
    accept = actions.add_parser("accept", help="zaakceptuj pokazaną wersję wyniku")
    correct = actions.add_parser("correct", help="zapisz korektę pola pokazanego w wyniku")
    for action in (show, accept, correct):
        action.add_argument("pdf", help="względna ścieżka PDF-u z review list")
    for action in (accept, correct):
        action.add_argument("--expect", required=True, metavar="REVIEW_ID",
                            help="identyfikator wersji wyniku z review show")
    correct.add_argument("--field", required=True, help="ścieżka pola, np. przelew_bankowy.kwota")
    correct.add_argument("--value", required=True, help="nowa wartość w składni JSON")
    args = parser.parse_args()
    if args.ocr_max_pages < 0:
        parser.error("--ocr-max-pages musi być nieujemne")
    input_dir, output_dir, diagnostic = (path.resolve() for path in (args.input, args.output, args.diagnostics))
    if (overlaps(input_dir, output_dir) or overlaps(diagnostic, input_dir)
            or overlaps(diagnostic, output_dir)):
        parser.error("Wejście, wyjście i diagnostyka muszą mieć odrębne ścieżki")
    state = state_directory(output_dir)
    if overlaps(diagnostic, state) or overlaps(input_dir, state):
        parser.error("Ścieżka ewidencji wyników koliduje z wejściem lub diagnostyką")
    if args.command == "review":
        journal = journal_path(diagnostic)
        if any(overlaps(journal, root) for root in (input_dir, output_dir, state)):
            parser.error("Ścieżka dziennika decyzji koliduje z wejściem, wyjściem lub ewidencją")
    try:
        if args.command == "review":
            with output_lock(output_dir):
                try:
                    return run_review(args, input_dir, output_dir, diagnostic)
                except (KeyError, TypeError, AttributeError) as exc:
                    raise ValueError("Nieprawidłowa struktura diagnostyki lub konfiguracji.") from exc
        ocr = prepare_ocr(args.ocr_data) if args.ocr_data else None
        return process(input_dir, output_dir, load_classes(args.config), diagnostic, ocr,
                       ocr_page_budget=args.ocr_max_pages)
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
