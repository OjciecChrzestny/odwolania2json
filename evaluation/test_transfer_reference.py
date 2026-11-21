"""Transaction reference extraction through the normal document entry point."""
import unittest

from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


FIELD = "przelew_bankowy.numer_transakcji"
RECEIPT = (
    "POTWIERDZENIE PRZELEWU\nKwota: 12,50 PLN\nData operacji: 2026-06-05\n"
    "Rachunek nadawcy: 64111111111111111111111111\nOpis: Materialy\nStatus: WYKONANO\n"
)

CASES = {
    "two_ids": ("Numer referencyjny dokumentu: WYD-017\nNumer transakcji: 0007", "0007"),
    "document_only": ("Numer referencyjny dokumentu: WYD-017", None),
    "empty_after_print_id": ("ID dokumentu:\nWYD-017\nNr ref.:", None),
    "daily_id": ("Dzienny numer transakcji: 0025", "0025"),
    "daily_one_digit": ("Dzienny numer transakcji: 7", "7"),
    "bank_reference": ("Referencja klienta: K-991\nReferencje banku: 00006571 004", "00006571004"),
    "bank_qualified_reference": ("Nr transakcji w Banku Testowym: 000071 Data operacji: 2026-06-05", "000071"),
    "number_below_label": ("Transaction reference number:\n\n000877", "000877"),
    "no_id": ("Numer wydruku: PRT-029\nOpis transakcji: umowa A-19", None),
    "plain_account": ("Numer transakcji: 64111111111111111111111111", None),
    "spaced_account": ("Referencje banku:\n64 1111 1111 1111 1111 1111 1111", None),
    "iban": ("Nr ref.: PL64111111111111111111111111", None),
    "foreign_iban": ("Reference number: DE89370400440532013000", None),
    "date": ("Numer referencyjny:\n2026-06-05", None),
    "description": ("Numer transakcji: w rozliczeniu A-193", None),
    "letters_only": ("Nr ref.: UTT", None),
    "reference_with_slashes": ("Numer transakcji: 1/7/7.", "1/7/7"),
}


class TransferReferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def parse(self, *pages):
        data, diag = extract(Document.from_pages(pages), self.classes)
        self.assertEqual(diag["class"], "przelew")
        return data["przelew_bankowy"]["numer_transakcji"], diag["fields"].get(FIELD)

    def test_label_and_complete_value(self):
        for case, (lines, expected) in CASES.items():
            with self.subTest(case=case):
                value, evidence = self.parse(RECEIPT + lines)
                self.assertEqual(value, expected)
                if expected is None:
                    self.assertIsNone(evidence)
                else:
                    self.assertEqual(evidence["page"], 1)

    def test_does_not_read_a_bare_value_on_the_next_page(self):
        value, evidence = self.parse(RECEIPT + "Numer transakcji:", "0032\nData wydruku: 2026-06-06")
        self.assertIsNone(value)
        self.assertIsNone(evidence)

    def test_later_transaction_id_supersedes_daily_id_with_correct_page(self):
        value, evidence = self.parse(RECEIPT + "Dzienny numer transakcji: 0025",
                                     "Numer transakcji: 2026-06-05\nReferencja banku: REF-0904")
        self.assertEqual(value, "REF-0904")
        self.assertEqual(evidence["page"], 2)
