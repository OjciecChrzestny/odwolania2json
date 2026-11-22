"""Physical source positions for references on scanned transfers."""
import unittest

from odwolania2json.bank_scan import ScanView, Word
from odwolania2json.model import Document, Extraction, load_classes
from odwolania2json.transfer_reference import PATH, apply_scan_reference


def view(*rows, page=2):
    positions = tuple(tuple(Word(x, 16 * y, width, 10, text) for x, width, text in row)
                      for y, row in enumerate(rows))
    return ScanView(page, "", (), positions=positions)


class ScanTransactionReferenceTest(unittest.TestCase):
    def recover(self, *views):
        document = Document.from_pages(("Pismo przewodnie", "Potwierdzenie przelewu"))
        result = Extraction(document, load_classes()["przelew"]["schema"])
        apply_scan_reference(result, views)
        field = ".".join(PATH)
        return result.data[PATH[0]][PATH[1]], result.evidence.get(field)

    def test_two_detached_columns(self):
        columns = view(((20, 36, "Numer"), (62, 60, "transakcji"), (200, 35, "Numer"), (242, 45, "wydruku")),
                       ((25, 54, "00A-527"), (204, 56, "WYD-013")))
        value, evidence = self.recover(columns)
        self.assertEqual(value, "00A-527")
        self.assertEqual((evidence["page"], evidence["source"]), (2, "ocr"))

    def test_different_widths_with_reference_in_second_column(self):
        columns = view(((10, 32, "Numer"), (48, 55, "dokumentu"), (390, 58, "Referencje"), (454, 30, "banku")),
                       ((13, 45, "WYD-987"), (396, 43, "tA001")))
        self.assertEqual(self.recover(columns)[0], "tA001")

    def test_misleading_headings_or_values(self):
        for heading, value in (
            ("Numer referencyjny dokumentu", "00A-527"),
            ("Numer faktury", "FV/52"),
            ("Identyfikator sprawy", "AB-123"),
            ("Numer transakcji:", "PL64111111111111111111111111"),
            ("Numer transakcji:", "XX1234"),
            ("Numer transakcji:", "XX-1234"),
            ("Numer transakcji:", "2026-05-04"),
        ):
            with self.subTest(heading=heading):
                self.assertEqual(self.recover(view(((20, 145, heading),), ((24, 95, value),))), (None, None))

    def test_competing_readings_or_wrong_page_do_not_fill(self):
        entry = ((20, 31, "Numer"), (56, 45, "transakcji:"))
        entry += ((220, 44, "Numer"), (270, 35, "faktury"))
        first = view(entry, ((20, 55, "K-4312"),))
        second = view(entry, ((20, 55, "K-4318"),))
        self.assertEqual(self.recover(first, second), (None, None))
        self.assertEqual(self.recover(view(entry, ((20, 55, "K-4312"),), page=3)), (None, None))


    def test_empty_id_skips_nearby_unlabelled_print_number(self):
        heading = ((60, 40, "Numer"), (102, 67, "transakcji:"))
        print_id = ((60, 68, "PRINT-081"),)
        print_heading = ((60, 55, "Numer"), (120, 55, "wydruku"))
        self.assertEqual(self.recover(view(heading, print_id, print_heading)), (None, None))


    def test_wrapped_heading_and_value_on_upper_line(self):
        top = ((46, 42, "Numer"), (172, 67, "003519"))
        bottom = ((44, 65, "transakcji"),)
        value, detail = self.recover(view(top, bottom))
        self.assertEqual(value, "003519")
        self.assertEqual(detail["page"], 2)

    def test_wrapped_foreign_heading_is_not_an_id(self):
        top = ((46, 42, "Numer"), (172, 67, "003519"))
        for suffix in ("faktury", "wydruku", "rachunku", "sprawy"):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.recover(view(top, ((44, 65, suffix),))), (None, None))

    def test_explicit_reference_below_skewed_table_header(self):
        heading = ((390, 40, "Numer"), (439, 65, "referencyjny"), (511, 71, "transakcji"))
        other_column = ((200, 95, "2026-06-05"),)
        number = ((389, 60, "RZ9-0044"),)
        self.assertEqual(self.recover(view(heading, other_column, number))[0], "RZ9-0044")


    def test_split_masked_row_is_not_an_id(self):
        top = ((46, 42, "Numer"), (170, 8, "*"), (182, 50, "1228"))
        bottom = ((44, 65, "transakcji"),)
        self.assertEqual(self.recover(view(top, bottom)), (None, None))
