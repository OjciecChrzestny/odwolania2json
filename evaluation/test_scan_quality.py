"""Page-read observations follow the PDF reader without changing extraction."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PageObject, PdfWriter
from pypdf.errors import PdfReadError

from odwolania2json.extract import ReadError, extract, read_pdf
from odwolania2json.model import Document, load_classes
from test_baseline_a import write_pdf


TRANSFER = """POTWIERDZENIE PRZELEWU
Data operacji: 2026-01-02
Kwota: 12,50 PLN
Z rachunku: 00123456789012345678901234
Na rachunek: 00987654321098765432109876
Opis: Wpis za odwolanie
Numer transakcji: 0000123"""


class PageQualityTest(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.classes = load_classes()

    def pdf(self, *texts):
        result = self.root / "test.pdf"
        pdf = PdfWriter()
        for index, text in enumerate(texts):
            if text:
                page = self.root / f"page-{index}.pdf"
                write_pdf(page, text)
                pdf.append(page)
            else:
                pdf.add_blank_page(width=600, height=800)
        pdf.write(result)
        return result

    def test_appeal_reads_image_only_pages_within_the_extraction_limit(self):
        path = self.pdf("", "", "", "")
        native = ["Krajowa Izba Odwoławcza\nOdwołujący: Fikcyjna spółka\nZamawiający: Fikcyjna gmina\nODWOŁANIE", "Opis sprawy", ""]
        calls = []

        def scanner(_pdf, stop, *, start):
            calls.append((start, stop))
            return [(start, "Zarzut 1: Zaniechanie odrzucenia oferty.")]

        with patch.object(PageObject, "extract_text", side_effect=native):
            document, pages = read_pdf(path, scanner, max_pages=3, classes=self.classes)

        value, report = extract(document, self.classes)
        self.assertEqual(calls, [(2, 3)])
        self.assertEqual(pages, [3])
        self.assertEqual(value["OdwolanieKIO"]["czynnosc_powod_id"], 7)
        self.assertEqual(report["first_allegation"]["page"], 3)
        self.assertFalse(report["first_allegation"]["fallback"])
        self.assertEqual(document.scan_quality["pages"][3]["reason"], "page_limit")

    def test_native_reference_on_seventh_page_has_source_page(self):
        path = self.pdf(TRANSFER.split("Numer transakcji:")[0], *["Dalsza czesc dokumentu"] * 5,
                        "Numer transakcji: 0007")
        document, ocr_pages = read_pdf(path, classes=self.classes, ocr_page_budget=0)
        data, diagnostic = extract(document, self.classes)
        self.assertEqual(ocr_pages, [])
        self.assertEqual(data["przelew_bankowy"]["numer_transakcji"], "0007")
        self.assertEqual(diagnostic["fields"]["przelew_bankowy.numer_transakcji"]["page"], 7)
        self.assertEqual(document.scan_quality["pages"][6]["reason"], "native_text")

    def test_only_ocr_attempts_spend_budget_including_failed_reads(self):
        path = self.pdf(*[""] * 10)
        native = ["Krajowa Izba Odwoławcza\nOdwołujący: Fikcyjna spółka\nZamawiający: Fikcyjna gmina\nODWOŁANIE",
                  *["Pouczenie do odwołania"] * 5, "", "", "", "Czytelny koniec"]
        calls = []

        def scan(_path, stop, *, start):
            calls.append((start, stop))
            return [(start, "Odczyt strony" if start == 6 else "")]

        with patch.object(PageObject, "extract_text", side_effect=native):
            document, ocr_pages = read_pdf(path, scan, classes=self.classes, ocr_page_budget=2)
        self.assertEqual(calls, [(6, 7), (7, 8)])
        self.assertEqual(ocr_pages, [7])
        pages = document.scan_quality["pages"]
        self.assertEqual((pages[7]["reason"], pages[8]["reason"], pages[9]["reason"]),
                         ("ocr_no_text", "ocr_page_budget", "native_text"))

    def test_zero_budget_never_calls_scanner(self):
        path = self.pdf("", "Czytelny zalacznik")
        def scanner(*args, **kwargs):
            self.fail("zero budget must not render a page")
        document, attempted = read_pdf(path, scanner, classes=self.classes, ocr_page_budget=0)
        self.assertEqual(attempted, [])
        self.assertEqual(document.scan_quality["pages"][0]["reason"], "ocr_page_budget")

    def test_native_readability_and_extraction_are_separate(self):
        text = TRANSFER.replace("Kwota: 12,50 PLN", "Kwota: 12,50 PLN\nKwota: 26,50 PLN")
        path = self.pdf(text)
        document, ocr_pages = read_pdf(path, classes=self.classes)
        self.assertEqual(ocr_pages, [])
        report = document.scan_quality
        self.assertEqual((report["status"], report["reason"], report["review_pages"]),
                         ("readable", "all_pages_readable", []))
        self.assertEqual([(page["page"], page["status"], page["source"], page["reason"])
                          for page in report["pages"]], [(1, "readable", "text", "native_text")])
        self.assertNotIn("Kwota", json.dumps(report))
        self.assertEqual(extract(document, self.classes), extract(Document.from_pages([text]), self.classes))

    def test_sparse_ocr_remains_in_reader_output_even_when_page_is_partial(self):
        path = self.pdf("")
        calls = []

        def scanner(pdf, limit):
            calls.append((pdf, limit))
            return [(0, "przelew 100 PLN")]

        document, ocr_pages = read_pdf(path, scanner)
        self.assertEqual(calls, [(path, 1)])
        self.assertEqual(ocr_pages, [1])
        self.assertIn("przelew 100 PLN", document.text)
        page, = document.scan_quality["pages"]
        self.assertEqual((page["status"], page["reason"], page["source"], page["tokens"]),
                         ("partial", "ocr_sparse_text", "ocr", 3))
        self.assertEqual(document.scan_quality["review_pages"], [1])

    def test_failed_middle_page_is_visible_and_later_native_text_is_kept(self):
        path = self.pdf("PISMO PRZEWODNIE", "", "Zalacznik numer trzy")
        calls = []

        def scanner(pdf, stop, *, start=0):
            calls.append((start, stop))
            return [(start, "")]

        document, ocr_pages = read_pdf(path, scanner, classes=self.classes)
        self.assertEqual(calls, [(1, 2)])
        self.assertEqual(ocr_pages, [])
        self.assertIn("Zalacznik numer trzy", document.text)
        report = document.scan_quality
        self.assertEqual((report["status"], report["review_pages"]), ("partial", [2]))
        self.assertEqual([page["reason"] for page in report["pages"]],
                         ["native_text", "ocr_no_text", "native_text"])

    def test_native_first_page_does_not_hide_a_bad_middle_page(self):
        path = self.pdf(TRANSFER, "", "Zalacznik numer trzy")
        document, ocr_pages = read_pdf(path, classes=self.classes)
        self.assertEqual(ocr_pages, [])
        self.assertEqual(document.scan_quality["review_pages"], [2])
        self.assertEqual([page["reason"] for page in document.scan_quality["pages"]],
                         ["native_text", "ocr_not_configured", "native_text"])

    def test_page_limit_and_no_ocr_selection_have_different_reasons(self):
        path = self.pdf(TRANSFER, "", "Zalacznik numer trzy", "Tekst poza limitem")

        def scanner(*args, **kwargs):
            self.fail("The existing extraction path skips OCR once the transfer is classified")

        document, ocr_pages = read_pdf(path, scanner, max_pages=3, classes=self.classes)
        report = document.scan_quality
        self.assertEqual((report["status"], report["page_count"], report["review_pages"]), ("partial", 4, [2, 4]))
        self.assertEqual([(page["page"], page["status"], page["reason"]) for page in report["pages"]], [
            (1, "readable", "native_text"), (2, "unassessed", "ocr_not_selected"),
            (3, "readable", "native_text"), (4, "unassessed", "page_limit"),
        ])
        self.assertNotIn("Tekst poza limitem", document.text)
        self.assertEqual(ocr_pages, [])

    def test_scanner_without_a_page_result_differs_from_empty_ocr(self):
        path = self.pdf("", "")
        with self.assertRaisesRegex(ReadError, "^brak czytelnej tre") as result:
            read_pdf(path, lambda pdf, limit: [(0, "")])
        report = result.exception.scan_quality
        self.assertEqual(report["reason"], "no_readable_content")
        self.assertEqual([(page["status"], page["reason"]) for page in report["pages"]],
                         [("unreadable", "ocr_no_text"), ("unassessed", "ocr_no_page_result")])

    def test_render_error_preserves_previous_results_and_original_exception(self):
        path = self.pdf("", "")
        failure = RuntimeError("render failed")

        def scanner(pdf, limit):
            yield (0, "Potwierdzenie przelewu bankowego z oplata za rozpatrzenie odwolania.")
            raise failure

        with self.assertRaises(RuntimeError) as result:
            read_pdf(path, scanner)
        self.assertIs(result.exception, failure)
        report = failure.scan_quality
        self.assertEqual((report["reason"], report["review_pages"]), ("ocr_failed", [2]))
        self.assertEqual([page["reason"] for page in report["pages"]], ["ocr_text", "ocr_interrupted"])

    def test_native_error_marks_failed_page_and_aborted_pages(self):
        path = self.pdf(TRANSFER, "Fragment testowy", "Trzecia strona", "Czwarta strona")
        failure = ValueError("bad page stream")
        with patch.object(PageObject, "extract_text", side_effect=[TRANSFER, failure]):
            with self.assertRaises(ValueError) as result:
                read_pdf(path, max_pages=3)
        self.assertIs(result.exception, failure)
        report = failure.scan_quality
        self.assertEqual(report["reason"], "native_read_failed")
        self.assertEqual([page["reason"] for page in report["pages"]],
                         ["native_text", "native_read_failed", "native_read_aborted", "page_limit"])

    def test_native_numeric_fragment_remains_available_to_extraction(self):
        path = self.pdf(TRANSFER, "123 456")
        document, ocr_pages = read_pdf(path, classes=self.classes)
        self.assertEqual(ocr_pages, [])
        self.assertIn("123 456", document.text)
        page = document.scan_quality["pages"][1]
        self.assertEqual((page["status"], page["reason"], page["source"], page["alphanumeric_chars"]),
                         ("partial", "native_fragment", "text", 6))

    def test_invalid_pdf_has_no_known_page_count_and_a_distinct_open_error(self):
        path = self.root / "bad.pdf"
        path.write_bytes(b"not a PDF")
        with self.assertRaises(PdfReadError) as result:
            read_pdf(path)
        self.assertEqual(result.exception.scan_quality, {
            "status": "unassessed", "reason": "pdf_open_failed", "page_count": None,
            "pages": [], "review_pages": [],
        })

    def test_encrypted_pdf_preserves_read_error_and_reports_encryption(self):
        path = self.root / "encrypted.pdf"
        pdf = PdfWriter()
        pdf.add_blank_page(width=600, height=800)
        pdf.encrypt("synthetic")
        pdf.write(path)
        with self.assertRaisesRegex(ReadError, "PDF jest zaszyfrowany") as result:
            read_pdf(path)
        self.assertEqual(result.exception.scan_quality["reason"], "pdf_encrypted")
        self.assertIsNone(result.exception.scan_quality["page_count"])
