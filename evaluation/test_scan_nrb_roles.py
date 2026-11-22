"""Check Polish account evidence without any external samples or OCR engine."""
from dataclasses import replace
from unittest import TestCase

from odwolania2json.bank_accounts import PAYEE, PAYER, account_observations, valid_nrb
from odwolania2json.bank_scan import ScanView, Word, row_text
from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


def nrb(body):
    return f"{98 - int(body + '252100') % 97:02d}" + body


LEFT = nrb("001122334455667788990011")
RIGHT = nrb("998877665544332211009988")
OTHER = nrb("123412341234123412341234")
LABELS = {PAYER: "Rachunek nadawcy", PAYEE: "Rachunek odbiorcy"}


def columns(left, right, *, payer_on_left):
    left_role, right_role = (PAYER, PAYEE) if payer_on_left else (PAYEE, PAYER)
    return (
        (Word(20, 10, 145, 16, LABELS[left_role]), Word(350, 10, 145, 16, LABELS[right_role])),
        (Word(20, 45, 230, 16, left), Word(350, 45, 230, 16, right)),
    )


class ScanNRBRolesTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def extracted(self, *layouts, primary=""):
        views = [ScanView(1, "", row_text(rows), positions=rows) for rows in layouts]
        original = Document.from_pages(["Potwierdzenie przelewu\nKwota: 85,00 PLN\n" + primary])
        doc = replace(original, bank_scan=lambda: views)
        data, info = extract(doc, self.classes)
        self.assertEqual(info["class"], "przelew")
        bank = data["przelew_bankowy"]
        return bank[PAYER], bank[PAYEE]

    def test_explicit_pl_and_leading_zero_are_kept_in_either_role(self):
        for payer_left in (True, False):
            with self.subTest(payer_left=payer_left):
                areas = [columns(left, RIGHT, payer_on_left=payer_left)
                         for left in ("PL" + LEFT, "PL " + LEFT)]
                want = ("PL" + LEFT, RIGHT) if payer_left else (RIGHT, "PL" + LEFT)
                self.assertEqual(self.extracted(*areas), want)
        self.assertTrue(valid_nrb("PL" + LEFT))
        self.assertFalse(valid_nrb("DE" + LEFT))

    def test_prefix_cannot_be_borrowed_from_adjacent_column(self):
        area = columns(LEFT, "PL " + RIGHT, payer_on_left=False)
        result = self.extracted(area, area)
        self.assertEqual(result, ("PL" + RIGHT, LEFT))

    def test_invalid_and_noisy_value_leaves_correct_other_side(self):
        for noise in (LEFT[1:], LEFT[:-1] + "I", LEFT[:-1] + str((int(LEFT[-1]) + 1) % 10)):
            with self.subTest(noise=noise):
                self.assertEqual(self.extracted(columns(noise, RIGHT, payer_on_left=False)), (RIGHT, None))

    def test_conflict_between_two_real_values_preserves_other_account(self):
        left = columns(LEFT, RIGHT, payer_on_left=False)
        conflicting = columns(OTHER, RIGHT, payer_on_left=False)
        self.assertEqual(self.extracted(left, conflicting), (RIGHT, None))

    def test_checksum_does_not_assign_same_number_to_both_roles(self):
        self.assertEqual(self.extracted(columns(LEFT, LEFT, payer_on_left=False)), (None, None))

    def test_identifiable_foreign_account_is_not_a_party(self):
        rows = ("Nadawca", LEFT, "Rachunek techniczny " + OTHER, "Odbiorca", RIGHT)
        self.assertEqual(account_observations(rows), {PAYER: {LEFT}, PAYEE: {RIGHT}})

    def test_account_under_generic_owned_section_requires_direction_and_counterparty(self):
        values = ("Dane rachunku", "Numer rachunku " + LEFT, "Dane kontrahenta", "Numer rachunku " + RIGHT)
        for context, expected in (("Przelew wychodzący", {PAYER: {LEFT}, PAYEE: {RIGHT}}),
                                  ("Przelew przychodzący", {PAYER: {RIGHT}, PAYEE: {LEFT}}),
                                  ("", {})):
            with self.subTest(context=context):
                self.assertEqual(account_observations((*values, context)), expected)
        self.assertEqual(account_observations((*values[:2], "Przelew wychodzący")), {})

    def test_isolated_account_cell_beside_date_keeps_its_own_role(self):
        def row(y, label, number):
            return (Word(20, y, 100, 16, "22.10.2026"),
                    Word(350, y, 120, 16, label + ":"),
                    Word(478, y, 226, 16, number))
        rows = (row(10, "Na rachunek", RIGHT), row(44, "Z rachunku", LEFT))
        self.assertEqual(self.extracted(rows), (LEFT, RIGHT))
        crowded = ((Word(20, 10, 100, 16, "Opis operacji dotyczącej"),
                    Word(125, 10, 120, 16, "Na rachunek:"),
                    Word(250, 10, 226, 16, OTHER)),)
        self.assertEqual(self.extracted(crowded), (None, None))

    def test_neutral_counterparty_requires_direction_and_its_own_section(self):
        lines = ("Rachunek zleceniodawcy " + LEFT, "Nazwa zleceniodawcy przykład",
                 "Dane kontrahenta", "Rachunek kontrahenta " + RIGHT)
        self.assertEqual(account_observations(lines), {PAYER: {LEFT}})
        self.assertEqual(account_observations(("Przelew wychodzący", *lines)),
                         {PAYER: {LEFT}, PAYEE: {RIGHT}})
        self.assertEqual(account_observations(("Przelew wychodzący", lines[0], lines[-1])),
                         {PAYER: {LEFT}})
        self.assertEqual(account_observations((*lines, "Tytuł: przelew wychodzący")), {PAYER: {LEFT}})

    def test_refund_and_copy_blocks_do_not_supply_counterparty_even_with_direction(self):
        for heading in ("Dane do zwrotu opłaty", "Kopia dla podmiotu rozliczającego"):
            with self.subTest(heading=heading):
                lines = ("Przelew wychodzący", "Rachunek nadawcy " + LEFT, heading,
                         "Dane kontrahenta", "Rachunek kontrahenta PL" + OTHER)
                self.assertEqual(account_observations(lines), {PAYER: {LEFT}})
                rows = tuple((Word(20, i * 25, 230, 16, line),) for i, line in enumerate(lines))
                self.assertEqual(self.extracted(rows), (LEFT, None))

    def test_cross_role_single_view_spill_does_not_override_agreement(self):
        exact = columns(LEFT, RIGHT, payer_on_left=True)
        only_wrong_payer = ((Word(20, 10, 145, 16, LABELS[PAYER]),),
                            (Word(20, 45, 230, 16, RIGHT),))
        separate = columns(RIGHT, LEFT, payer_on_left=False)
        self.assertEqual(self.extracted(exact, only_wrong_payer, separate), (LEFT, RIGHT))
        self.assertEqual(self.extracted(exact, only_wrong_payer), (None, None))

    def test_source_account_heading_binds_only_the_next_number_field(self):
        heading = "Przelew z rachunku: Szczegóły transakcji"
        self.assertEqual(account_observations((heading, "Numer rachunku " + LEFT)),
                         {PAYER: {LEFT}})
        self.assertEqual(account_observations((heading, "Numer rachunku VAT " + OTHER)), {})
        self.assertEqual(account_observations((heading, "Data operacji", "Numer rachunku " + OTHER)), {})

    def test_explicit_payer_section_does_not_infer_undirected_counterparty(self):
        lines = ("Dane zleceniodawcy", "Numer rachunku " + LEFT,
                 "Nazwa zleceniodawcy przykład", "Dane kontrahenta", "Rachunek kontrahenta " + RIGHT)
        self.assertEqual(account_observations(lines), {PAYER: {LEFT}})
        self.assertEqual(account_observations(("Przelew wychodzący", *lines)),
                         {PAYER: {LEFT}, PAYEE: {RIGHT}})

    def test_literal_pl_survives_legacy_digits_when_only_primary_scan_exists(self):
        original = Document.from_pages(["\n".join((
            "Potwierdzenie przelewu", "Kwota: 85,00 PLN",
            f"Rachunek nadawcy: PL{LEFT}", f"Rachunek odbiorcy: {RIGHT}",
        ))])
        scanned = replace(original, scan_quality={"pages": [{"page": 1, "source": "ocr"}]})
        for document in (scanned, replace(scanned, bank_scan=lambda: [ScanView(1, "", ("",))])):
            data, _ = extract(document, self.classes)
            self.assertEqual(data["przelew_bankowy"][PAYER], "PL" + LEFT)
            self.assertEqual(data["przelew_bankowy"][PAYEE], RIGHT)
