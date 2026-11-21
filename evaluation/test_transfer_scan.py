"""Regression checks for evidence from weak transfer scans."""
from dataclasses import replace
import unittest
from unittest.mock import Mock

from odwolania2json.bank_scan import ScanView, numeric_boxes, recovered_numbers, visual_rows
from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


def view(*rows, page=1):
    return ScanView(page, "\n".join(rows), rows)


class TransferScanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def test_geometry_restores_rows_in_a_column_first_page(self):
        def word(x, y, text):
            return f"5\t1\t1\t1\t1\t1\t{x}\t{y}\t45\t12\t90\t{text}"
        tsv = "\n".join((word(0, 40, "Kwota"), word(0, 65, "Data"), word(40, 65, "operacji"),
                         word(190, 39, "1 234,50"), word(190, 67, "2024-02-29")))
        self.assertEqual(visual_rows(tsv), ("Kwota 1 234,50", "Data operacji 2024-02-29"))

    def test_dates_are_valid_and_booking_is_a_fallback(self):
        scan = view("Data wystawienia 2026-04-04", "Data księgowania 2026-04-03",
                    "Data realizacji 31.02.2026", "Data operacji 02.04.2026",
                    "Opłata 4,25 PLN", "Kwota przelewu -1 234, 50 PLN")
        self.assertEqual(recovered_numbers([scan, scan]),
                         {"data_operacji": ("2026-04-02", 1), "kwota": (1234.5, 1)})

    def test_a_fee_and_print_date_do_not_supply_a_value(self):
        scan = view("Kwota", "Opłata 5,00 PLN", "Data realizacji", "Data wystawienia 03.02.2026")
        self.assertEqual(recovered_numbers([scan, scan]), {})

    def test_conflicting_or_uncorroborated_digits_remain_unknown(self):
        first = view("Kwota 200,80 PLN", "Data operacji 2 lipca 2026")
        second = view("Kwota 200,00 PLN", "Data operacji m lipca 2026")
        self.assertEqual(recovered_numbers([first, second]), {})
        self.assertEqual(recovered_numbers([first]), {})
        other_page = view("Kwota 200,80 PLN", page=2)
        self.assertEqual(recovered_numbers([first, other_page]), {})

    def test_crop_evidence_is_tied_to_a_unique_full_token_on_its_page(self):
        rows = ("Data operacji 01.04.2026", "Kwota 29 004,00 PLN")
        coords = "5\t1\t1\t1\t1\t1\t160\t25\t75\t14\t82\t"
        words = "\n".join(coords + value for value in ("01.04.2026", "29", "004,00", "PLN"))
        self.assertEqual(numeric_boxes(words, rows, {"kwota", "data_operacji"}),
                         [("data_operacji", "2026-04-01", (160, 25, 75, 14))])
        self.assertEqual(numeric_boxes(words + "\n" + coords + "01.04.2026", rows, {"data_operacji"}), [])
        sparse = ScanView(1, "", rows, (("data_operacji", "2026-04-01"),))
        self.assertEqual(recovered_numbers([sparse]), {"data_operacji": ("2026-04-01", 1)})
        conflict = view("Data operacji 02.04.2026")
        self.assertNotIn("data_operacji", recovered_numbers([sparse, conflict]))

    def test_pair_without_labels_is_confined_to_a_pure_numeric_row(self):
        a = view("Polecenie przelewu", "PLN 93.25 14.01.2026")
        self.assertEqual(recovered_numbers([a, a]), {"kwota": (93.25, 1), "data_operacji": ("2026-01-14", 1)})
        b = view("Opłata i data wydruku", "PLN 93.25 14.01.2026")
        self.assertEqual(recovered_numbers([b, b]), {})

    def test_native_values_and_negative_invoices_skip_recovery(self):
        forbidden = Mock(side_effect=AssertionError("unexpected bank OCR"))
        for raw in ("Potwierdzenie przelewu\nKwota 12,25 PLN\nData operacji 2026-07-12",
                    "FAKTURA VAT\nDo zapłaty 12,25 PLN\nSposób zapłaty przelew"):
            doc = replace(Document.from_pages([raw]), bank_scan=forbidden)
            extract(doc, self.classes)
        forbidden.assert_not_called()

    def test_fill_only_the_missing_field_and_record_the_page(self):
        raw = "Potwierdzenie przelewu\nKwota 17,00 PLN"
        scan = view("Kwota 999,00 PLN", "Data realizacji 2026-03-04", page=2)
        reader = Mock(return_value=[scan, scan])
        doc = replace(Document.from_pages([raw, "Szczegóły"]), bank_scan=reader)
        result, diagnostics = extract(doc, self.classes)
        self.assertEqual(result["przelew_bankowy"]["kwota"], 17)
        self.assertEqual(result["przelew_bankowy"]["data_operacji"], "2026-03-04")
        self.assertEqual(diagnostics["fields"]["przelew_bankowy.data_operacji"]["page"], 2)
        reader.assert_called_once()

    def test_structural_cue_requires_a_transfer_heading(self):
        details = "PL64 1111 1111 1111 1111 1111 1111\n1 234,50 PLN 2026-05-06"
        for heading, expected in (("POLECENIE PRZELEWU", "przelew"), ("ZAMÓWIENIE", "negative"),
                                  ("FAKTURA VAT\nPOLECENIE PRZELEWU", "negative")):
            with self.subTest(heading=heading):
                _, status = extract(Document.from_pages([heading + "\n" + details]), self.classes)
                self.assertEqual(status["class"], expected)
