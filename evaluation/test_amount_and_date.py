"""Transfer numbers must be taken from the columns that name those fields."""
from dataclasses import replace
import unittest
from unittest.mock import Mock

from odwolania2json.bank_scan import ScanView, recovered_numbers
from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


class AmountAndDateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def test_flattened_columns_override_booking_and_provide_source_page(self):
        document = Document.from_pages([
            "Potwierdzenie przelewu\nStatus: Zrealizowano\nKwota przelewu\nData księgowania: 04.04.2026",
            "Data wydruku  Data wykonania\n06.04.2026  03.04.2026\n"
            "Saldo po operacji  Kwota przelewu  Prowizja\n9 505,44 PLN  −154, 56 PLN  12,00 PLN",
        ])
        value, diagnostics = extract(document, self.classes)
        fields = value["przelew_bankowy"]
        self.assertEqual((fields["kwota"], fields["data_operacji"]), (154.56, "2026-04-03"))
        for key in ("kwota", "data_operacji"):
            self.assertEqual(diagnostics["fields"][f"przelew_bankowy.{key}"],
                             {"page": 2, "rule": "kwota_i_data_w_kolumnach"})

    def test_alternative_ocr_views_keep_the_labels_bound_to_their_values(self):
        rows = (
            "Data wydruku Data realizacji Data księgowania",
            "06.04.2026 03.04.2026 04.04.2026",
            "Saldo po operacji Kwota przelewu Prowizja",
            "9 505,44 PLN 154,56 PLN 12,00 PLN",
        )
        views = [ScanView(1, "\n".join(rows), rows) for _ in range(2)]
        scan = Mock(return_value=views)
        document = replace(Document.from_pages(["Potwierdzenie przelewu\nStatus: Zrealizowano\nRachunek odbiorcy"]), bank_scan=scan)
        value, diagnostics = extract(document, self.classes)
        fields = value["przelew_bankowy"]
        self.assertEqual((fields["kwota"], fields["data_operacji"]), (154.56, "2026-04-03"))
        self.assertEqual(diagnostics["fields"]["przelew_bankowy.kwota"]["rule"], "ocr_wiersz_kwoty")
        scan.assert_called_once()

    def test_spaces_between_separator_and_cents_preserve_the_whole_amount(self):
        document = Document.from_pages([
            "Potwierdzenie przelewu\nKwota przelewu: 1 054, 56 PLN"
            "\nSaldo po operacji: 9 505,44 PLN\nStatus: Zrealizowano"
        ])
        value, _ = extract(document, self.classes)
        self.assertEqual(value["przelew_bankowy"]["kwota"], 1054.56)

    def test_inline_cells_use_their_own_label(self):
        rows = (
            "Saldo po operacji 9 505,44 PLN Kwota przelewu 154,56 PLN Kwota prowizji 12,00 PLN",
            "Data wydruku 06.04.2026 Data wykonania 03.04.2026 Data księgowania 04.04.2026",
        )
        scan = ScanView(1, "", rows)
        self.assertEqual(recovered_numbers([scan, scan]),
                         {"kwota": (154.56, 1), "data_operacji": ("2026-04-03", 1)})

    def test_missing_or_wrongly_typed_cells_cannot_shift_remaining_values(self):
        for rows in (
            ("Saldo po operacji Kwota przelewu Prowizja", "9 505,44 PLN 12,00 PLN"),
            ("Kwota przelewu Prowizja", "154,56 PLN 06.04.2026"),
            ("Data wydruku Data wykonania", "06.04.2026"),
            ("Data wydruku Data wykonania", "06.04.2026 31.02.2026"),
            ("Kwota prowizji 12,00 PLN", "Data wydruku 06.04.2026"),
            ("Kwota przelewu Saldo po operacji", "Kwota prowizji 12,00 PLN"),
        ):
            with self.subTest(rows=rows):
                scan = ScanView(1, "", rows)
                self.assertEqual(recovered_numbers([scan, scan]), {})

    def test_table_with_wrong_execution_date_can_supply_only_the_booking_date(self):
        rows = ("Data wydruku Data wykonania Data księgowania", "06.04.2026 31.02.2026 04.04.2026")
        scan = ScanView(1, "", rows)
        self.assertEqual(recovered_numbers([scan, scan]), {"data_operacji": ("2026-04-04", 1)})

    def test_unsupported_or_unbounded_money_tokens_are_ignored(self):
        for amount in ("١٢,٣٤", "9" * 400 + ",00"):
            with self.subTest(amount=amount):
                rows = (f"Kwota przelewu {amount} PLN", "Data wykonania 03.04.2026")
                scan = ScanView(1, "", rows)
                self.assertEqual(recovered_numbers([scan, scan]), {"data_operacji": ("2026-04-03", 1)})
