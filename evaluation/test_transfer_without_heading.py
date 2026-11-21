"""Classification of executed transfers presented as operation details."""
from dataclasses import replace
import unittest
from unittest.mock import Mock

from odwolania2json.bank_scan import ScanView
from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


DETAILS = (
    "Szczegóły operacji",
    "Rodzaj operacji: przelew wychodzący",
    "Data księgowania: 17.04.2025",
    "Kwota operacji: -143,25 PLN",
    "Nadawca: Podmiot A",
    "Odbiorca: Podmiot B",
)


class TransferWithoutHeadingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def check(self, lines, expected, *, scan=None):
        document = replace(Document.from_pages(["\n".join(lines)]), bank_scan=scan)
        data, diagnostics = extract(document, self.classes)
        self.assertEqual(diagnostics["class"], expected)
        if expected == "negative":
            self.assertIsNone(data)
        return diagnostics

    def test_booked_transfer_in_operation_details(self):
        diagnostics = self.check(DETAILS, "przelew")
        signal = next(s for s in diagnostics["signals"]
                      if s["rule"] == "zaksięgowany_przelew_w_szczegółach_operacji")
        self.assertEqual(signal["page"], 1)
        self.assertIn("data_księgowania", signal["criteria"])

    def test_booking_amount_and_transfer_type_share_the_same_table_row(self):
        header = "Rodzaj operacji | Data księgowania | Kwota"
        values = "Przelew wychodzący | 17.04.2025 | -143,25 PLN"
        diagnostics = self.check((header, values, *DETAILS[4:]), "przelew")
        self.assertIn("zaksięgowany_przelew_w_wierszu_operacji",
                      [signal["rule"] for signal in diagnostics["signals"]])
        self.check((header, values.replace(" | 17.04.2025", ""), "17.04.2025", *DETAILS[4:]),
                   "negative")
        self.check((header, values.replace("Przelew wychodzący", "Zwrot kartowy"),
                    *DETAILS[4:], "Tytuł: przelew wychodzący"), "negative")

    def test_lookalikes_without_executed_transfer(self):
        for label, replacement in (
            ("empty", ("Rodzaj operacji: przelew wychodzący", "Data księgowania:",
                       "Kwota operacji:", "Nadawca:", "Odbiorca:")),
            ("card", ("Rodzaj operacji: płatność kartą", *DETAILS[2:],
                      "Tytuł: zwrot za przelew")),
            ("invoice", (*DETAILS[1:], "FAKTURA VAT nr FV/12")),
            ("pending", (*DETAILS[1:], "Status operacji: oczekująca")),
            ("split_status", (*DETAILS[1:], "Stan operacji:", "oczekuje na autoryzację")),
            ("print_date", (DETAILS[1], "Data wydruku: 17.04.2025", *DETAILS[3:])),
            ("fee", (*DETAILS[1:3], "Opłata: 143,25 PLN", *DETAILS[4:])),
            ("no_payer", (*DETAILS[1:4], DETAILS[5])),
        ):
            with self.subTest(label=label):
                self.check((DETAILS[0], *replacement), "negative")

    def test_direction_with_account_owner_and_counterparty(self):
        details = (
            "Dane właściciela rachunku", "Spółka X",
            "Dane beneficjenta / Zleceniodawcy", "Spółka Y",
            "Szczegóły operacji",
            "Opis kodu operacji: krajowa płatność wychodząca",
            "Referencje banku: BANK1234567",
            *DETAILS[2:4],
        )
        self.check(details, "przelew")
        self.check(tuple(line.replace("/ Zleceniodawcy", "/ nieczytelne") for line in details), "przelew")
        self.check(tuple(line for line in details if not line.startswith("Referencje banku")), "negative")
        self.check(tuple(line.replace("Opis kodu operacji:", "Tytuł:") for line in details), "negative")

    def test_another_page_cannot_supply_booking(self):
        document = Document.from_pages(["\n".join((*DETAILS[:2], *DETAILS[3:])), DETAILS[2]])
        self.assertEqual(extract(document, self.classes)[1]["class"], "negative")

    def test_alternate_ocr_uses_complete_details(self):
        scan = Mock(return_value=[ScanView(1, "\n".join(DETAILS), DETAILS)])
        diagnostics = self.check((DETAILS[0], "Data księgowania", "Rodzaj operacji"), "przelew", scan=scan)
        scan.assert_called_once()
        self.assertTrue(diagnostics["classification_from_ocr_layout"])

    def test_excluded_page_skips_alternate_ocr(self):
        scan = Mock(side_effect=AssertionError("unexpected alternate OCR"))
        self.check((*DETAILS, "Status operacji: do autoryzacji"), "negative", scan=scan)
        scan.assert_not_called()
