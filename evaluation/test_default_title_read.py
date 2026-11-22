"""Zwykły punkt wejścia wykorzystuje drugi lokalny odczyt strony tytułowej."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pypdf import PdfWriter

from evaluation.test_appeal_procedure import COVER
from odwolania2json.__main__ import process
from odwolania2json.appeal_procedure import DocumentWithVerifiedTitle, observed_title
from odwolania2json.model import Document, load_classes


class DefaultTitleReadTests(unittest.TestCase):
    def test_confirmed_title_reaches_json_and_diagnostics(self):
        text = (COVER + "\nDotyczy: zamówienia pn. „Budowa Czytelni”, nr referencyjny: NP/54/26\n"
                "Wnoszę odwołanie wobec zmiany SWZ.")
        first_read = Document.from_pages([text])
        original, reference, offset = observed_title(text)
        second_read = DocumentWithVerifiedTitle(
            first_read.text, first_read.starts, original_title=original, verified_title="Budowa czytelni",
            procedure_reference=reference, title_offset=offset,
        )
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "input"
            inputs.mkdir()
            pdf = inputs / "pismo.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=400, height=600)
            writer.write(pdf)
            diagnostics = root / "diagnostics.json"
            classes = load_classes()
            ocr = object()
            with (patch("odwolania2json.extract.read_pdf", return_value=(first_read, [1])) as read,
                  patch("odwolania2json.appeal_procedure.verify_cover_title", return_value=second_read) as verify):
                result = process(inputs, root / "output", classes, diagnostics, ocr, ocr_page_budget=2)
            self.assertEqual(result, 0)
            read.assert_called_once_with(pdf, ocr, classes=classes, ocr_page_budget=2)
            verify.assert_called_once_with(pdf, first_read, [1], ocr, classes)
            value = json.loads((root / "output/pismo.json").read_text())
            self.assertEqual(value["ZamowieniePubliczne"]["tytul"], "Budowa czytelni")
            field = json.loads(diagnostics.read_text())["documents"][0]["fields"]["ZamowieniePubliczne.tytul"]
            self.assertEqual((field["source"], field["page"]), ("ocr", 1))
