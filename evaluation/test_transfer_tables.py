"""Bank roles, posted status and evidence in flattened transfer pages."""
import unittest

from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


class TransferLayoutTest(unittest.TestCase):
    payer = "64111111111111111111111111"
    payee = "85222222222222222222222222"

    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def parse(self, *lines):
        return extract(Document.from_pages(["\n".join(lines)]), self.classes)

    def test_incoming_and_outgoing_owner_account(self):
        for direction, amount, counterparty_heading, expected in (
                ("Incoming transfer", "8.20", "Payer", (self.payer, self.payee)),
                ("Outgoing transfer", "-8.20", "Beneficiary", (self.payee, self.payer))):
            with self.subTest(direction=direction):
                roles = []
                for heading in ("Beneficiary", "Payer"):
                    roles.append(heading)
                    if heading == counterparty_heading:
                        roles.append("Account number PL" + self.payer)
                data, diag = self.parse(
                    "Transfer confirmation", "Account details", "Account number PL" + self.payee,
                    *roles, "Transaction details", direction, "Amount " + amount,
                    "Booking date 2026-03-03", "Execution date 2026-03-01", "Title Materials",
                )
                bank = data["przelew_bankowy"]
                self.assertEqual((bank["z_rachunku"], bank["na_rachunek"]), expected)
                self.assertEqual((bank["kwota"], bank["data_operacji"], bank["tytul"]), (8.2, "2026-03-01", "Materials"))
                self.assertIsNone(bank["numer_transakcji"])
                self.assertEqual(diag["fields"]["przelew_bankowy.z_rachunku"]["page"], 1)

    def test_owner_without_direction_is_not_assigned(self):
        data, _ = self.parse("Transfer confirmation", "Account details", "Account number PL" + self.payer,
                             "Payer", "Beneficiary", "Transaction details", "Amount 12.50")
        bank = data["przelew_bankowy"]
        self.assertIsNone(bank["z_rachunku"])
        self.assertIsNone(bank["na_rachunek"])

    def test_order_and_leading_zero_in_two_columns(self):
        for headings, accounts in (("Płatnik Beneficjent", (self.payer, self.payee)),
                                   ("Beneficjent Płatnik", (self.payee, self.payer))):
            with self.subTest(headings=headings):
                data, _ = self.parse("Potwierdzenie wykonania operacji", headings,
                                     "Firma X Firma Y", " ".join(accounts), "Kwota operacji Data transakcji",
                                     "1 234,50 PLN 2026-03-02", "Nr ref.: 000123")
                self.assertEqual(data["przelew_bankowy"],
                                 dict(z_rachunku=self.payer, na_rachunek=self.payee, data_operacji="2026-03-02",
                                      kwota=1234.5, numer_transakcji="000123", tytul=None))

    def test_invoice_coupon_and_draft_are_negative(self):
        cases = [
            ("POTWIERDZENIE TRANSAKCJI", "do faktury nr FV/7", "Rachunek odbiorcy: " + self.payee, "Kwota: 39,00"),
            ("POTWIERDZENIE TRANSAKCJI", "Sklep spożywczy", "Kwota: 39,00"),
            ("Transaction confirmation", "Amount 39.00", "Product: ticket"),
            ("POTWIERDZENIE PRZELEWU", "Kwota: 39,00", "Rachunek odbiorcy: " + self.payee, "Status: do autoryzacji"),
            ("Transfer confirmation", "Amount 39.00", "Transaction status PENDING"),
        ]
        for lines in cases:
            with self.subTest(lines=lines):
                data, diag = self.parse(*lines)
                self.assertIsNone(data)
                self.assertEqual(diag["class"], "negative")

    def test_account_from_another_section_is_not_copied(self):
        data, _ = self.parse("POTWIERDZENIE PRZELEWU", "Kwota: 1,00", "Rachunek zleceniodawcy",
                             "Firma X", "PLXX (nieczytelny)", "Odbiorca Firma Y",
                             "Rachunek odbiorcy PL" + self.payee)
        self.assertIsNone(data["przelew_bankowy"]["z_rachunku"])
        self.assertEqual(data["przelew_bankowy"]["na_rachunek"], self.payee)

    def test_stacked_headers_without_alignment(self):
        data, _ = self.parse("POTWIERDZENIE PRZELEWU", "Kwota: 1,00", "Płatnik", "Odbiorca",
                             "", "Firma X", "", "PL" + self.payer, "", "Firma Y", "", "PL" + self.payee)
        self.assertIsNone(data["przelew_bankowy"]["z_rachunku"])
        self.assertIsNone(data["przelew_bankowy"]["na_rachunek"])

    def test_empty_reference_does_not_copy_an_iban_or_next_label(self):
        data, _ = self.parse("POTWIERDZENIE PRZELEWU", "Kwota: 1,00", "PL" + self.payer,
                             "Nr ref.:", "Status: ZREALIZOWANO")
        self.assertIsNone(data["przelew_bankowy"]["numer_transakcji"])

    def test_title_preserves_paragraph_boundary(self):
        data, _ = self.parse("POLECENIE PRZELEWU", "Kwota:", "", "57,00 PLN", "Opis: Zaliczka",
                             "", "Materiały informacyjne w załączeniu")
        self.assertEqual(data["przelew_bankowy"]["tytul"], "Zaliczka")
        self.assertEqual(data["przelew_bankowy"]["kwota"], 57.0)
