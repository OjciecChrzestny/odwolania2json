"""Publiczny interfejs wiersza poleceń."""
import argparse
import json
import logging
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from tempfile import NamedTemporaryFile

from pypdf.errors import PyPdfError

from .extract import extract, read_pdf
from .model import DEFAULT_CONFIG, load_classes
from .ocr import prepare_ocr

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


def process(input_dir, output_dir, classes, diagnostics, ocr=None, *,
            read_document=read_pdf, extract_document=extract):
    input_dir.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(path for path in input_dir.rglob("*")
                  if path.suffix.lower() == ".pdf" and path.is_file())
    sources = {p.relative_to(input_dir).with_suffix(".json").as_posix(): p for p in pdfs}
    if len({os.path.normcase(name) for name in sources}) != len(pdfs):
        raise ValueError("Kilka wejściowych PDF-ów wskazuje ten sam wynik")

    output_dir.mkdir(parents=True, exist_ok=True)
    state = state_directory(output_dir)
    if state.is_symlink():
        raise ValueError(f"Ewidencja wyników jest dowiązaniem symbolicznym: {state}")
    state.mkdir(exist_ok=True)
    journal, lock_file = state / "owned", state / "lock"
    if journal.is_symlink() or lock_file.is_symlink():
        raise ValueError(f"Plik ewidencji wyników jest dowiązaniem symbolicznym: {state}")
    with closing(sqlite3.connect(lock_file)) as lock:
        lock.execute("BEGIN IMMEDIATE")
        owned = set(json.loads(journal.read_text(encoding="utf-8"))) if journal.exists() else set()
        for name in owned | sources.keys():
            path = target(output_dir, name)
            if path.exists() and (name not in owned or not path.is_file()):
                raise ValueError(f"Istniejący plik poza ewidencją wyników {path}")
        # Rezerwacja przed zapisaniem wyników pozwala wznowić przerwany przebieg.
        write_file(journal, json_bytes(sorted(owned | sources.keys())))
        current, records = set(), []
        for name, pdf in sorted(sources.items()):
            try:
                document, ocr_pages = read_document(pdf, ocr, classes=classes)
            except (OSError, ValueError, PyPdfError, KeyError, TypeError, RuntimeError, IndexError, OverflowError) as exc:
                logging.error("%s — błąd odczytu (%s)", name, type(exc).__name__)
                records.append({"output": name, "class": "read_error", "status": "read_error",
                                "error": str(exc), "fields": {}})
                continue
            value, record = extract_document(document, classes)
            write_file(target(output_dir, name), b"" if value is None else json_bytes(value))
            current.add(name)
            records.append({"output": name, **record, "ocr_pages": ocr_pages})
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
    parser.add_argument("--ocr-data", type=Path, help="katalog pol.traineddata dla opcjonalnego OCR")
    args = parser.parse_args()
    input_dir, output_dir, diagnostic = (path.resolve() for path in (args.input, args.output, args.diagnostics))
    if (overlaps(input_dir, output_dir) or overlaps(diagnostic, input_dir)
            or overlaps(diagnostic, output_dir)):
        parser.error("Wejście, wyjście i diagnostyka muszą mieć odrębne ścieżki")
    state = state_directory(output_dir)
    if overlaps(diagnostic, state) or overlaps(input_dir, state):
        parser.error("Ścieżka ewidencji wyników koliduje z wejściem lub diagnostyką")
    try:
        ocr = prepare_ocr(args.ocr_data) if args.ocr_data else None
        return process(input_dir, output_dir, load_classes(args.config), diagnostic, ocr)
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
