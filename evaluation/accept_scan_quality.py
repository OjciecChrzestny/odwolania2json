"""Generate isolated synthetic DEV PDFs and probe the normal read/extract path."""
import argparse
import json
from contextlib import closing
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

from odwolania2json.__main__ import process
from odwolania2json.extract import read_pdf
from odwolania2json.model import load_classes
from odwolania2json.ocr import prepare_ocr
from test_baseline_a import write_pdf
from test_scan_quality import TRANSFER


EXPECTED = {
    "native.pdf": [("readable", "native_text")],
    "weak.pdf": [("partial", "ocr_sparse_text")],
    "bad-middle.pdf": [("readable", "native_text"), ("unreadable", "ocr_no_text"),
                       ("readable", "native_text")],
    "page-limit.pdf": [("readable", "native_text")] * 6 + [("unassessed", "page_limit")],
    "conflict.pdf": [("readable", "native_text")],
    # Manually legible sparse text is a conservative false review.
    "sparse-readable.pdf": [("partial", "ocr_sparse_text")],
    "strong.pdf": [("readable", "ocr_text")],
    "bad-pdf.pdf": [],
}

MANUAL_DEV = {name: [state for state, _ in pages] for name, pages in EXPECTED.items()}
MANUAL_DEV["sparse-readable.pdf"] = ["readable"]
MANUAL_DEV["page-limit.pdf"] = ["readable"] * 7


def pdf_from_raster(source, destination, scale):
    from pypdfium2 import PdfDocument

    with closing(PdfDocument(source)) as pdf, closing(pdf[0]) as page:
        width, height = page.get_size()
        with closing(page.render(scale=scale, grayscale=True)) as bitmap:
            raw = bytes(bitmap.buffer)
            image = DecodedStreamObject()
            image.set_data(b"".join(raw[row:row + bitmap.width]
                                    for row in range(0, bitmap.stride * bitmap.height, bitmap.stride)))
            image.update({
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Image"),
                NameObject("/Width"): NumberObject(bitmap.width),
                NameObject("/Height"): NumberObject(bitmap.height),
                NameObject("/ColorSpace"): NameObject("/DeviceGray"),
                NameObject("/BitsPerComponent"): NumberObject(8),
            })

    result = PdfWriter()
    target = result.add_blank_page(width=width, height=height)
    image_ref = result._add_object(image.flate_encode())
    target[NameObject("/Resources")] = DictionaryObject({
        NameObject("/XObject"): DictionaryObject({NameObject("/Scan"): image_ref}),
    })
    contents = DecodedStreamObject()
    contents.set_data(f"q {width} 0 0 {height} 0 0 cm /Scan Do Q".encode("ascii"))
    target.replace_contents(contents)
    result.write(destination)


def obscure(source, destination, bottom, height):
    writer = PdfWriter(clone_from=source)
    page = writer.pages[0]
    contents = DecodedStreamObject()
    mask = f"\n0 g 32 {bottom} 380 {height} re f\n".encode("ascii")
    contents.set_data(page.get_contents().get_data() + mask)
    page.replace_contents(contents)
    writer.write(destination)


def prepare(work):
    source, parts = work / "input", work / "parts"
    source.mkdir(parents=True)
    parts.mkdir()
    write_pdf(source / "native.pdf", TRANSFER)
    write_pdf(source / "conflict.pdf", TRANSFER.replace("Kwota: 12,50 PLN", "Kwota: 12,50 PLN\nKwota: 26,50 PLN"))
    write_pdf(parts / "weak-native.pdf", "Fragment 100 PLN\nDalsza tresc odczytu\nKolejny szczegol")
    obscure(parts / "weak-native.pdf", parts / "weak.pdf", bottom=705, height=40)
    write_pdf(parts / "legible.pdf", "Pismo przewodnie")
    write_pdf(parts / "strong.pdf", "To jest czytelna strona testowa z dlugim tekstem bez danych osobowych.")
    write_pdf(parts / "cover.pdf", "PISMO PRZEWODNIE")
    write_pdf(parts / "appendix.pdf", "Zalacznik do dokumentu testowego")
    obscure(parts / "appendix.pdf", parts / "empty.pdf", bottom=724, height=54)
    pdf_from_raster(parts / "weak.pdf", source / "weak.pdf", scale=1.25)
    pdf_from_raster(parts / "legible.pdf", source / "sparse-readable.pdf", scale=2.0)
    pdf_from_raster(parts / "strong.pdf", source / "strong.pdf", scale=2.0)
    pdf_from_raster(parts / "empty.pdf", parts / "damaged.pdf", scale=1.25)
    pdf = PdfWriter()
    for part in ("cover.pdf", "damaged.pdf", "appendix.pdf"):
        pdf.append(parts / part)
    pdf.write(source / "bad-middle.pdf")
    pdf = PdfWriter()
    for _ in range(7):
        pdf.append(parts / "appendix.pdf")
    pdf.write(source / "page-limit.pdf")
    (source / "bad-pdf.pdf").write_bytes(b"broken PDF")


def probe(work, name, tessdata, require_observations):
    from pypdfium2 import PdfPage

    result = work / name
    result.mkdir()
    readings = {}
    ocr = prepare_ocr(tessdata)

    def measured_reader(path, ocr, *, classes):
        started = perf_counter()
        try:
            document, ocr_pages = read_pdf(path, ocr, classes=classes)
        except Exception as exc:
            readings[path.name] = {
                "seconds": perf_counter() - started,
                "scan_quality": getattr(exc, "scan_quality", None),
                "error": type(exc).__name__,
            }
            raise
        readings[path.name] = {
            "seconds": perf_counter() - started,
            "scan_quality": getattr(document, "scan_quality", None),
            "ocr_pages": ocr_pages,
        }
        return document, ocr_pages

    render = PdfPage.render
    render_calls = 0

    def counted_render(page, *args, **kwargs):
        nonlocal render_calls
        render_calls += 1
        return render(page, *args, **kwargs)

    started = perf_counter()
    with patch.object(PdfPage, "render", counted_render):
        exit_code = process(work / "input", result / "output", load_classes(), result / "cli.json",
                            ocr, read_document=measured_reader)
    summary = {"seconds": perf_counter() - started, "cli_exit": exit_code,
               "render_calls": render_calls, "documents": readings}
    if require_observations:
        statuses = {}
        for name, entry in readings.items():
            report = entry["scan_quality"]
            assert report is not None, name
            pages = report["pages"]
            statuses[name] = [(page["status"], page["reason"]) for page in pages]
        summary["observed_statuses"] = statuses
        summary["page_count"] = sum(map(len, statuses.values()))
        summary["unassessed_pages"] = sum(state == "unassessed" for pages in statuses.values() for state, _ in pages)
        summary["manual_errors"] = [
            {"file": name, "page": index, "manual": expected, "observed": observed}
            for name, pages in statuses.items()
            for index, ((observed, _), expected) in enumerate(zip(pages, MANUAL_DEV[name]), 1)
            if observed != "unassessed" and observed != expected
        ]
    (result / "observations.json").write_text(json.dumps(summary, indent=2) + "\n")
    assert exit_code == 1 and set(readings) == set(EXPECTED), summary
    if require_observations:
        assert readings["bad-pdf.pdf"]["scan_quality"]["reason"] == "pdf_open_failed"
        assert readings["bad-middle.pdf"]["scan_quality"]["review_pages"] == [2]
        assert statuses == EXPECTED, statuses
    print(result / "observations.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generator = subparsers.add_parser("prepare")
    generator.add_argument("work", type=Path)
    runner = subparsers.add_parser("probe")
    runner.add_argument("work", type=Path)
    runner.add_argument("name")
    runner.add_argument("tessdata", type=Path)
    runner.add_argument("--expect-observations", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.work.resolve())
    else:
        probe(args.work.resolve(), args.name, args.tessdata, args.expect_observations)


if __name__ == "__main__":
    main()
