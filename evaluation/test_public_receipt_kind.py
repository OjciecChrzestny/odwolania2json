"""Classify one executed bank transfer with evidence local to its operation."""
from dataclasses import replace
import unittest
from unittest.mock import Mock

from odwolania2json.bank_scan import ScanView
from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


BOOKED = (
    "Szczegóły transakcji",
    "Typ transakcji / opis",
    "731 PRZELEW Z RACHUNKU",
    "Data księgowania: 2025-04-17 11:23",
    "Kwota: -123,45 PLN",
    "Z rachunku: 11 1234 1111 2222 3333 4444 5555",
    "Na rachunek: 21 4321 1111 2222 3333 4444 5555",
    "Nr transakcji: TA-218",
)


BANK_RECEIPT = (
    "POTWIERDZENIE WYKONANIA PRZELEWU",
    "Status: wykonany",
    "Z rachunku: 14 2222 1111 2222 4444 7777 0101",
    "Na rachunek: 25 4321 1111 2222 3333 5555 0101",
    "Kwota: 381,22 PLN",
    "Data operacji: 2025-05-22",
    "Numer transakcji: TX-1947",
)


class PublicReceiptKindTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def parse(self, *pages, scan=None):
        doc = Document.from_pages(["\n".join(rows) for rows in pages])
        return extract(replace(doc, bank_scan=scan), self.classes)

    def assert_negative(self, *rows):
        value, report = self.parse(rows)
        self.assertEqual(report["class"], "negative")
        self.assertIsNone(value)

    def test_posted_type_and_booking_with_time_without_confirmation_title(self):
        value, report = self.parse(BOOKED)
        self.assertEqual(report["class"], "przelew")
        self.assertIn("przelew_bankowy", value)
        self.assertTrue(any(signal["page"] == 1 for signal in report["signals"]))

    def test_an_independent_operational_trace_is_required(self):
        details = tuple(line for line in BOOKED if not line.startswith(("Data księgowania", "Nr transakcji")))
        self.assert_negative(*details, "Data wydruku: 2025-04-18")

    def test_booked_card_with_ocr_damage_and_transfer_word_in_memo(self):
        self.assert_negative(
            "Szczegóły operacji",
            "Rodzaj operacji: płatno kart,",
            "Status operacji: zaksięgowana",
            "Kwota: 38,70 PLN",
            "Data księgowania: 2025-03-12",
            "Akceptant: Punkt Testowy",
            "Opis operacji: przelew domowy",
        )

    def test_refund_type_and_transfer_memo_have_different_roles(self):
        refund = tuple("Zwrot płatności kartowej" if "731 PRZELEW" in row else row for row in BOOKED)
        self.assert_negative(*refund, "Status operacji: zaksięgowana", "Tytuł: zwrot za przelew")
        _, report = self.parse((*BOOKED, "Tytuł: zwrot nadpłaty"))
        self.assertEqual(report["class"], "przelew")

    def test_multi_operation_statement_and_example_table_are_negative(self):
        self.assert_negative("Wyciąg z rachunku", *BOOKED,
                             "18.04.2025 PŁATNOŚĆ KARTĄ -20,00 PLN", "Saldo końcowe: 100,01 PLN")
        self.assert_negative("Instrukcja", "Przykład bankowego potwierdzenia:", *BOOKED)
        self.assert_negative("KUPON PŁATNICZY", *BOOKED)
        self.assert_negative("VOUCHER", *BOOKED)

    def test_cancelled_and_future_instruction_are_negative(self):
        self.assert_negative(*BOOKED, "Status operacji: anulowana")
        planned = tuple("Planowana data wykonania: 2025-04-17"
                        if row.startswith("Data księgowania") else row for row in BOOKED)
        self.assert_negative("Potwierdzenie złożenia dyspozycji", *planned)

    def test_unrelated_later_mention_is_not_the_transfer_status(self):
        context = ("Historia zgłoszenia", "Poprzednia dyspozycja anulowana.",
                   "Opis: zwrot rozliczono w osobnym dokumencie.")
        _, report = self.parse((*BOOKED, *context))
        self.assertEqual(report["class"], "przelew")

    def test_alternate_bank_rows_can_supply_the_same_page_evidence(self):
        first = ("Szczegóły transakcji", "Typ transakcji", "Data księgowania",
                 "Z rachunku", "Na rachunek")
        alternative = ScanView(1, "Niepełny tekst po rozpoznaniu układu", BOOKED)
        scan = Mock(return_value=[alternative])
        _, report = self.parse(first, scan=scan)
        self.assertEqual(report["class"], "przelew")
        scan.assert_called_once()
        self.assertTrue(report["classification_from_ocr_layout"])

    def test_a_different_page_cannot_supply_booking_proof(self):
        first = tuple(line for line in BOOKED if not line.startswith(("Data księgowania", "Nr transakcji")))
        _, report = self.parse(first, ("Data księgowania: 2025-04-17", "Nr transakcji: INNA-741"))
        self.assertEqual(report["class"], "negative")

    def test_confirmation_table_requires_date_amount_and_transaction_type(self):
        rows = (
            "Potwierdzenie transakcji",
            "Kwota Data transakcji Numer referencyjny transakcji",
            "350,44 PLN 17.05.2025 TX-41",
            "Typ transakcji / nazwa",
            "841 Przelew krajowy",
            "Numer rachunku: 11 1234 1111 2222 3333 4444 5555",
            "Numer rachunku: 21 4321 1111 2222 3333 4444 5555",
        )
        _, report = self.parse(rows)
        self.assertEqual(report["class"], "przelew")
        self.assert_negative(*rows[:2], "350,44 PLN TX-41", *rows[3:])
        self.assert_negative(*rows[:5], "Numer rachunku:", "Numer rachunku:")
        self.assert_negative(*rows, "17.05.2025 Zapłata online -5,00 PLN",
                             "19.05.2025 Opłata okresowa -6,00 PLN")
        self.assert_negative(*rows[:4], "841 Zwrot kartowy", *rows[5:])
        self.assert_negative("Poradnik importu", "Przykład potwierdzenia:", *rows)

    def test_type_after_booked_details_and_value_date_still_supplies_evidence(self):
        rows = (
            "Przelew z rachunku: Szczegóły transakcji",
            "Numer rachunku 11 1234 1111 2222 3333 4444 5555",
            "Data waluty 2025-05-18",
            "Data operacji 2025-05-17",
            "Rachunek odbiorcy: Podmiot testowy",
            "Typ transakcji Przelew z rachunku",
            "Kwota -75,10 PLN",
        )
        _, report = self.parse(rows)
        self.assertEqual(report["class"], "przelew")
        self.assert_negative(*rows[:2], "Data wydruku 2025-05-18", *rows[3:])

    def test_ocr_separator_does_not_turn_an_unexecuted_order_into_a_receipt(self):
        rows = (
            "Przelew krajowy",
            "Szczegóły zlecenia",
            "Typ zlecenia Przelew",
            "Status . . wykonane",
            "Rachunea nadawcy 11 1234 1111 2222 3333 4444 5555",
            "Rachunek kontrahenta 21 4321 1111 2222 3333 4444 5555",
            "Szczegóły płatności 132.60 PLN",
        )
        _, report = self.parse(rows)
        self.assertEqual(report["class"], "przelew")
        self.assert_negative(*rows[:3], "Status . . niewykonane", *rows[4:])
        self.assert_negative(*rows[:3], "Status . . anulowane", *rows[4:])
        self.assert_negative(*rows[:3], "Planowana data wykonania 2025-04-18", *rows[4:])

    def test_instruction_at_opening_cannot_borrow_copied_bank_title(self):
        self.assert_negative("INSTRUKCJA BANKOWOŚCI INTERNETOWEJ", "Przykład formularza:", *BANK_RECEIPT)
        _, report = self.parse((*BANK_RECEIPT, "INSTRUKCJA BANKOWOŚCI"))
        self.assertEqual(report["class"], "przelew")

    def test_card_refund_identified_by_bare_type_is_negative(self):
        for type_line in ("Rodzaj: zwrot płatności kartą", "Typ: zwrot karty"):
            self.assert_negative("POTWIERDZENIE OPERACJI BANKOWEJ", type_line,
                                 "Kwota: 82,22 PLN", "Data operacji: 2025-05-22",
                                 "Numer transakcji: KK-512")

    def test_explicit_negation_refers_to_the_document_not_a_remittance_title(self):
        disclaimer = "Niniejszy wydruk nie stanowi potwierdzenia wykonania przelewu."
        staged = tuple(row for row in BANK_RECEIPT if not row.startswith("Status: "))
        self.assert_negative(*staged, "Status dyspozycji: zarejestrowana", disclaimer)
        self.assert_negative(*staged, "Nie jest potwierdzeniem realizacji operacji.")
        for title in ("Zwrot opłaty za kartę", disclaimer):
            value, report = self.parse((*BANK_RECEIPT, f"Tytuł: {title}"))
            self.assertEqual(report["class"], "przelew")
            self.assertEqual(value["przelew_bankowy"]["tytul"].rstrip("."), title.rstrip("."))
