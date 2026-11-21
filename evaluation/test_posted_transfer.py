"""Regression checks for settled transfers, unfilled instructions and OCR evidence."""
from dataclasses import replace
import unittest
from unittest.mock import Mock

from odwolania2json.bank_scan import ScanView
from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


class PostedTransferTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    amount = "Kwota transakcji: 1 257,49 PLN"
    value_date = "Data waluty: 09.04.2025"
    kind = "Typ produktu: przelew krajowy"
    reference = "Referencje banku: ABC0991"
    heading = "Szczegółowy raport z transakcji"

    def classify(self, *lines):
        return extract(Document.from_pages(["\n".join(lines)]), self.classes)[1]["class"]

    def test_confirmations_need_booked_transfer_evidence(self):
        for heading in (self.heading, "Potwierdzenie wykonanej operacji"):
            with self.subTest(heading=heading):
                self.assertEqual(self.classify(heading, self.amount, self.kind, self.value_date, self.reference), "przelew")
        for missing in range(4):
            detail = [self.amount, self.kind, self.value_date, self.reference]
            detail.pop(missing)
            with self.subTest(missing=missing):
                self.assertEqual(self.classify(self.heading, *detail), "negative")

    def test_card_draft_and_empty_form_are_negative(self):
        self.assertEqual(self.classify(self.heading, self.amount, self.value_date, self.reference,
                                       "Rachunek odbiorcy: 00376100310001020304051801",
                                       "Typ produktu: płatność kartą"), "negative")
        for status in ("do autoryzacji", "niezrealizowana", "zaplanowane"):
            self.assertEqual(self.classify(self.heading, self.amount, self.value_date, self.kind, self.reference,
                                           "Status: " + status), "negative")
        self.assertEqual(self.classify(self.heading, self.amount, self.value_date, self.kind, self.reference,
                                       "Tytuł: zwrot płatności kartą"), "przelew")
        self.assertEqual(self.classify("POLECENIE PRZELEWU", "Rachunek nadawcy:", "Rachunek odbiorcy:",
                                       "Kwota: ................ PLN", "Data operacji:", "Data wydruku 07.11.2025"),
                         "negative")

    def test_unrelated_pages_cannot_supply_a_missing_field(self):
        config = {**self.classes["przelew"], "classification_pages": 2}
        pages = [self.heading + "\n" + self.amount, "\n".join([self.kind, self.value_date, self.reference])]
        _, diag = extract(Document.from_pages(pages), {"przelew": config})
        self.assertEqual(diag["class"], "negative")
        pages[1] = self.heading + "\n" + self.amount + "\n" + pages[1]
        _, diag = extract(Document.from_pages(pages), {"przelew": config})
        self.assertEqual(diag["class"], "przelew")
        signal = next(s for s in diag["signals"] if s["rule"] == "rozliczona_operacja_z_danymi")
        self.assertEqual(signal["page"], 2)

    def test_alternate_ocr_uses_same_criteria(self):
        header = "Potwierdzenie wykonanej operacji"
        rows = (header, self.amount, self.value_date, self.kind, self.reference)
        for reading, expected in ((rows, "przelew"), (rows[:-1], "negative")):
            reader = Mock(return_value=[ScanView(1, "\n".join(reading), reading)])
            doc = replace(Document.from_pages([header]), bank_scan=reader)
            self.assertEqual(extract(doc, self.classes)[1]["class"], expected)
            reader.assert_called_once()
