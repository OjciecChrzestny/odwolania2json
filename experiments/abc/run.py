"""Przebieg B albo C ze wspólnym czytnikiem, selektorem i zapisem A."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
from time import perf_counter

from pypdf.errors import PyPdfError

from odwolania2json.__main__ import json_bytes, overlaps, process, write_file
from odwolania2json.extract import ReadError, extract, read_pdf
from odwolania2json.model import load_classes
from odwolania2json.ocr import prepare_ocr

from .adapters import Adapter, IDS, PROVIDERS, REASON_FIELD, https_post, sha256, shared_payload


def checked_descriptions(classes):
    lines = Path(__file__).with_name("uzp-reasons.txt").read_text(encoding="utf-8")
    pinned = dict(line.strip().split("=", 1) for line in lines.splitlines() if line.strip())
    descriptions = classes["odwolanie"]["reasons"]["descriptions"]
    if pinned != descriptions or set(pinned) != {str(reason_id) for reason_id in IDS}:
        raise ValueError("Słownik A nie odpowiada przypiętemu słownikowi UZP")
    return descriptions


def classify_document(document, classes, descriptions, adapter):
    value, record = extract(document, classes, capture_decision=True)
    fragment = record.pop("decision_fragment", None)
    record["a_sha256"] = sha256(b"" if value is None else json_bytes(value))
    if record["class"] != "odwolanie":
        return value, {**record, "experiment": {"outcome": "not_appeal", "attempted": False}}
    if fragment is None:
        return value, {**record, "experiment": {"outcome": "fallback",
                                                "cause": "no_reliable_fragment", "attempted": False}}

    source = record["first_allegation"]
    source["fragment_sha256"] = sha256(fragment.text.encode("utf-8"))
    source["start_offset"] = fragment.offset
    source["start_page"] = document.page(fragment.offset)
    source["end_page"] = document.page(fragment.offset + len(fragment.text) - 1)
    reason_id, report = adapter.classify(shared_payload(fragment.text, descriptions))
    if reason_id is None:
        return value, {**record, "experiment": {**report, "outcome": "fallback"}}

    section = value["OdwolanieKIO"]
    section[REASON_FIELD] = reason_id
    section["czynnosc_opis"] = descriptions[str(reason_id)]
    for field, rule in ((REASON_FIELD, "odpowiedź_modelu_dla_fragmentu"),
                        ("czynnosc_opis", "opis_kanoniczny_id")):
        record["fields"][f"OdwolanieKIO.{field}"] = {"page": source["page"], "rule": rule}
    return value, {**record, "experiment": {**report, "outcome": "success"}}


def run_variant(input_dir, run_dir, variant, *, token, transport, mode, ocr=None):
    input_dir, run_dir = input_dir.resolve(strict=True), run_dir.resolve()
    if not input_dir.is_dir() or overlaps(input_dir, run_dir):
        raise ValueError("Wejście i nowy katalog przebiegu muszą być odrębnymi katalogami")
    classes = load_classes()
    descriptions = checked_descriptions(classes)
    provider = PROVIDERS[variant]
    adapter = Adapter(provider, token, transport)
    run_dir.mkdir(parents=True)
    diagnostics = run_dir / "diagnostics" / "experiment.json"
    observations = {}
    current = None

    def read_document(path, local_ocr):
        nonlocal current
        current = observations[path.relative_to(input_dir).with_suffix(".json").as_posix()] = {
            "started": perf_counter(), "input_sha256": None,
        }
        try:
            with path.open("rb") as source:
                current["input_sha256"] = hashlib.file_digest(source, "sha256").hexdigest()
            return read_pdf(path, local_ocr)
        except (OSError, ValueError, PyPdfError, KeyError, TypeError, RuntimeError,
                IndexError, OverflowError) as exc:
            current["document_seconds"] = perf_counter() - current["started"]
            raise ReadError(type(exc).__name__) from None

    def extract_document(document, configs):
        value, record = classify_document(document, configs, descriptions, adapter)
        current["document_seconds"] = perf_counter() - current["started"]
        return value, record

    started = perf_counter()
    code = process(input_dir, run_dir / "output", classes, diagnostics, ocr,
                   read_document=read_document, extract_document=extract_document)
    batch_seconds = perf_counter() - started
    report = json.loads(diagnostics.read_bytes())
    for document in report["documents"]:
        details = observations[document["output"]]
        document.update(input_sha256=details["input_sha256"],
                        document_seconds=details["document_seconds"])
    report.update(mode=mode, variant=variant, model=provider.model, batch_seconds=batch_seconds)
    write_file(diagnostics, json_bytes(report))
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", required=True, choices=PROVIDERS)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path, help="nowy katalog przebiegu")
    parser.add_argument("--ocr-data", type=Path)
    parser.add_argument("--live", action="store_true", required=True,
                        help="jawna zgoda na przekazywanie fragmentów do wybranego API")
    args = parser.parse_args()
    provider = PROVIDERS[args.variant]
    logging.getLogger("pypdf").setLevel(logging.CRITICAL)
    ocr = prepare_ocr(args.ocr_data) if args.ocr_data else None
    return run_variant(args.input, args.run, args.variant, token=os.environ.get(provider.token_env, ""),
                       transport=https_post, mode="live", ocr=ocr)


if __name__ == "__main__":
    raise SystemExit(main())
