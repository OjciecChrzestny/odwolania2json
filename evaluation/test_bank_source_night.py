"""Bank evidence stays paired with the reading of its physical page."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import Mock

from odwolania2json.bank_scan import ScanView
from odwolania2json.extract import extract, transfer_from_alternate_page
from odwolania2json.model import Document, load_classes


class BankSourceNightTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def test_alternate_text_preserves_physical_metadata_without_reusing_another_tsv(self):
        views = [ScanView(1, "Potwierdzenie przelewu\nKwota: 27,16 PLN", ())]
        quality = {"pages": [{"page": 1, "source": "ocr"}, {"page": 2, "source": "text"}]}
        scan = Mock(return_value=views)
        primary = replace(
            Document.from_pages(["Bank\nniepełna treść przelewu", "Załącznik tekstowy"]),
            scan_quality=quality, bank_scan=scan, ocr_layout_tsv="TSV głównego odczytu",
        )
        selected, name, signals = transfer_from_alternate_page(primary, self.classes, views)
        self.assertEqual(name, "przelew")
        self.assertIn("Kwota: 27,16 PLN", selected.text)
        self.assertEqual(selected.page(selected.text.index("Załącznik tekstowy")), 2)
        self.assertIs(selected.scan_quality, quality)
        self.assertIs(selected.bank_scan, scan)
        self.assertIsNone(selected.ocr_layout_tsv)
        self.assertEqual({signal["page"] for signal in signals}, {1})
        scan.assert_not_called()

    def test_alternate_classification_reuses_views_and_keeps_other_page_number(self):
        selected = ScanView(1, "Potwierdzenie przelewu\nRachunek odbiorcy: brak", ())
        second = ScanView(2, "", ("Kwota: 47,83 PLN", "Data operacji 2026-04-05"))
        scan = Mock(return_value=[selected, second, second])
        primary = replace(Document.from_pages(["Bank przelew", "Oddzielna kartka skanu"]),
                          bank_scan=scan, ocr_layout_tsv="TSV innego odczytu")
        value, diagnostics = extract(primary, self.classes)
        self.assertEqual(diagnostics["class"], "przelew")
        self.assertTrue(diagnostics["classification_from_ocr_layout"])
        self.assertEqual(value["przelew_bankowy"]["kwota"], 47.83)
        self.assertEqual(value["przelew_bankowy"]["data_operacji"], "2026-04-05")
        self.assertEqual(diagnostics["fields"]["przelew_bankowy.kwota"]["page"], 2)
        self.assertEqual(diagnostics["fields"]["przelew_bankowy.data_operacji"]["page"], 2)
        scan.assert_called_once()
