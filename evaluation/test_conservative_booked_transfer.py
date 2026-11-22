"""Protect legacy execution scoring and check one booked transaction table."""
from copy import deepcopy
from unittest import TestCase

from odwolania2json.extract import extract
from odwolania2json.model import Document, class_candidate, classify, load_classes

NEW = "zaksięgowany_pojedynczy_przelew_w_tabeli"
OLD = "zaksięgowany_przelew"
COMMON = (
    "Bank regionalny\nNumer transakcji: TX-70336\nRachunek odbiorcy: brak danych\n"
    "Data Opis Kwota\nData operacji | PRZELEW krajowy 517,64 PLN\n"
    "Data księgowania: 2026-05-12"
)


class ConservativeBookedTransferTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()
        cls.baseline = deepcopy(cls.classes)
        cls.baseline["przelew"]["signals"] = [
            signal for signal in cls.baseline["przelew"]["signals"] if signal["name"] != NEW
        ]

    def test_transition_uses_posted_row_without_populating_guessed_amount(self):
        document = Document.from_pages([COMMON])
        self.assertEqual(classify(document, self.baseline)[0], "negative")
        result, trace = extract(document, self.classes)
        self.assertEqual(trace["class"], "przelew")
        self.assertIn(NEW, [signal["rule"] for signal in trace["signals"]])
        self.assertIsNone(result["przelew_bankowy"]["kwota"])

    def test_old_status_keeps_identical_evidence_and_score_even_with_new_table(self):
        document = Document.from_pages([COMMON + "\nStatus: zaksięgowana"])
        before = class_candidate(document, "przelew", self.baseline["przelew"], document.text)
        after = class_candidate(document, "przelew", self.classes["przelew"], document.text)
        self.assertIsNotNone(before)
        self.assertEqual(before, after)
        self.assertIn(OLD, [signal["rule"] for signal in after[2]])

    def test_old_status_without_table_is_not_replaced(self):
        page = "Raport banku\nRachunek odbiorcy: brak danych\nStatus: wykonana\nKwota: 90,12 PLN\nOpis: przelew"
        document = Document.from_pages([page])
        before = classify(document, self.baseline)
        self.assertEqual(before[0], "przelew")
        self.assertEqual(classify(document, self.classes), before)

    def test_rejects_card_statement_planned_order_and_refund(self):
        unsafe = (
            COMMON + "\nAkceptant: sklep",
            "Wyciąg bankowy\n" + COMMON,
            COMMON + "\n2026-05-13 PRZELEW 32,59 PLN",
            COMMON + "\nPlanowana data wykonania: 2026-05-13",
            COMMON.replace("PRZELEW krajowy", "PRZELEW ZWROT"),
            COMMON + "\nRodzaj operacji: refund",
        )
        for text in unsafe:
            with self.subTest(text=text):
                output, trace = extract(Document.from_pages([text]), self.classes)
                self.assertIsNone(output)
                self.assertEqual(trace["class"], "negative")

    def test_booking_must_be_filled_on_operation_page(self):
        incomplete = COMMON.rsplit(":", 1)[0] + ":"
        for document in (
            Document.from_pages([incomplete]),
            Document.from_pages([incomplete, "Data księgowania: 2026-05-12"]),
        ):
            with self.subTest(pages=len(document.starts)):
                self.assertEqual(classify(document, self.classes)[0], "negative")
