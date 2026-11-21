"""Regression checks for account ownership, page boundaries and ambiguous OCR."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import Mock

from odwolania2json.bank_accounts import PAYER, PAYEE, account_observations, valid_nrb
from odwolania2json.bank_scan import ScanView, Word, row_text
from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes
from odwolania2json.ocr import read_account_crops


def nrb_for(body):
    return f"{98 - int(body + '252100') % 97:02d}" + body


A = nrb_for("112233445566112233445566")
B = nrb_for("998877665544998877665544")
C = nrb_for("001122334455001122334455")


class AccountRoleTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def test_owner_requires_unambiguous_direction_and_changes_side(self):
        rows = ("Dane właściciela rachunku", "Rachunek właściciela PL" + A,
                "Dane beneficjenta/zleceniodawcy", "/" + B)
        for wording, expected in (("Obciążenie", {PAYER: {A}, PAYEE: {B}}),
                                  ("Uznanie", {PAYER: {B}, PAYEE: {A}}),
                                  ("", {}), ("Uznanie oraz obciążenie", {})):
            self.assertEqual(account_observations((*rows, wording)), expected)

    def test_reversed_columns_with_one_unreadable_value(self):
        rows = ((Word(10, 0, 90, 12, "Odbiorca"), Word(330, 0, 80, 12, "Nadawca")),
                (Word(12, 30, 190, 12, B), Word(331, 30, 195, 12, A[:-1])))
        self.assertEqual(account_observations(row_text(rows), rows), {PAYEE: {B}})
        self.assertEqual(account_observations(("Odbiorca Nadawca", B)), {})
        self.assertEqual(account_observations(("Odbiorca Nadawca", B + " " + A)),
                         {PAYEE: {B}, PAYER: {A}})

    def test_conflicting_account_numbers_mask_and_foreign_row_stay_unassigned(self):
        self.assertFalse(valid_nrb(A[:-1]))
        self.assertFalse(valid_nrb(A[:-1] + str((int(A[-1]) + 1) % 10)))
        self.assertEqual(account_observations(("Na rachunek: ****" + B[-20:], "Rachunek VAT " + C)), {})
        text = "POTWIERDZENIE PRZELEWU\nKwota: 12,00\nOdbiorca\n" + B + "\n" + C
        scan = ScanView(1, text, tuple(text.splitlines()))
        result, _ = extract(replace(Document.from_pages([text]), bank_scan=lambda: [scan]), self.classes)
        self.assertIsNone(result["przelew_bankowy"][PAYEE])

    def test_native_fallback_records_the_page_without_crossing_pages(self):
        first = "POTWIERDZENIE PRZELEWU\nKwota: 12,00\nRachunek właściciela\nPrzelew wychodzący"
        second = "Przelew wychodzący\n" + A + "\nDane kontrahenta\nNumer rachunku " + B
        result, info = extract(Document.from_pages([first, second]), self.classes)
        self.assertIsNone(result["przelew_bankowy"][PAYER])
        self.assertEqual(result["przelew_bankowy"][PAYEE], B)
        self.assertEqual(info["fields"]["przelew_bankowy.na_rachunek"]["page"], 2)

    def test_table_requires_executed_transaction_and_rejects_pending(self):
        lines = ("[ Potwierdzenie Transakcji ]", "Nr transakcji 123456 Data transakcji: 01.03.2026",
                 "Rachunek winien: Rachunek ma:", A + " " + B, "Kwota: 12,00")
        data, _ = extract(Document.from_pages(["\n".join(lines)]), self.classes)
        self.assertEqual((data["przelew_bankowy"][PAYER], data["przelew_bankowy"][PAYEE]), (A, B))
        for page in ("Rachunek winien: Rachunek ma:\nKwota:", "\n".join((*lines, "Status: do autoryzacji"))):
            self.assertIsNone(extract(Document.from_pages([page]), self.classes)[0])

    def test_crop_needs_two_matching_observed_readings(self):
        broken = A[:-1] + "I"
        position = ((Word(30, 60, 200, 16, broken),),)
        bitmap = Mock(buffer=b"0", width=400, height=800, n_channels=1, stride=400)
        for readings, expected in (((A, A), A), ((A, B), broken), ((A[:-1],), broken)):
            inner = Mock()
            inner.GetUTF8Text.side_effect = readings
            class Reader:
                def __init__(self, **kwargs): pass
                def __enter__(self): return inner
                def __exit__(self, *exc): pass
            recovered = read_account_crops(position, bitmap, Reader, ".")
            self.assertEqual(recovered[0][0].text, expected)
