"""Bank evidence stays paired with the reading of its physical page."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import Mock

from odwolania2json.bank_scan import ScanView, view_evidence
from odwolania2json.extract import extract, extract_class, transfer_from_alternate_page
from odwolania2json.model import Document, load_classes


class BankSourceNightTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def test_alternate_text_preserves_physical_metadata_without_reusing_another_tsv(self):
        views = [ScanView(1, "Potwierdzenie przelewu\nKwota: 27,16 PLN", ())]
        quality = {"pages": [{"page": 1, "source": "ocr"}, {"page": 2, "source": "text"}]}
        scan = Mock(return_value=views)
        primary = replace(
            Document.from_pages(["Bank\nniepełna treść przelewu", "Załącznik tekstowy"]),
            scan_quality=quality, bank_scan=scan, ocr_layout_tsv="TSV głównego odczytu",
        )
        selected, name, signals = transfer_from_alternate_page(primary, self.classes, views)
        self.assertEqual(name, "przelew")
        self.assertIn("Kwota: 27,16 PLN", selected.text)
        self.assertEqual(selected.page(selected.text.index("Załącznik tekstowy")), 2)
        self.assertIs(selected.scan_quality, quality)
        self.assertIs(selected.bank_scan, scan)
        self.assertIsNone(selected.ocr_layout_tsv)
        self.assertEqual({signal["page"] for signal in signals}, {1})
        scan.assert_not_called()

    def test_alternate_classification_reuses_views_and_keeps_other_page_number(self):
        selected = ScanView(1, "Potwierdzenie przelewu\nRachunek odbiorcy: brak", ())
        second = ScanView(2, "", ("Kwota: 47,83 PLN", "Data operacji 2026-04-05"))
        scan = Mock(return_value=[selected, second, second])
        primary = replace(Document.from_pages(["Bank przelew", "Oddzielna kartka skanu"]),
                          bank_scan=scan, ocr_layout_tsv="TSV innego odczytu")
        value, diagnostics = extract(primary, self.classes)
        self.assertEqual(diagnostics["class"], "przelew")
        self.assertTrue(diagnostics["classification_from_ocr_layout"])
        self.assertEqual(value["przelew_bankowy"]["kwota"], 47.83)
        self.assertEqual(value["przelew_bankowy"]["data_operacji"], "2026-04-05")
        self.assertEqual(diagnostics["fields"]["przelew_bankowy.kwota"]["page"], 2)
        self.assertEqual(diagnostics["fields"]["przelew_bankowy.data_operacji"]["page"], 2)
        scan.assert_called_once()

    def test_primary_tsv_can_confirm_alternate_value_without_reusing_its_text(self):
        text = "Bank przelew"
        row = "Kwota: 143,68 PLN"
        alternate = ScanView(1, "Potwierdzenie przelewu\nRachunek odbiorcy: brak", (row,))
        scan = Mock(return_value=[alternate])
        tsv = "\n".join(
            f"5\t1\t1\t1\t1\t{n}\t{x}\t15\t25\t12\t93\t{word}"
            for n, (x, word) in enumerate(((10, "Kwota:"), (50, "143,68"), (90, "PLN")), start=1)
        )
        primary = replace(Document.from_pages([text]), bank_scan=scan, ocr_layout_tsv=tsv)
        value, diagnostics = extract(primary, self.classes)
        self.assertEqual(value["przelew_bankowy"]["kwota"], 143.68)
        observation = diagnostics["fields"]["przelew_bankowy.kwota"]
        self.assertEqual((observation["page"], observation["source"], observation["precision"]), (1, "ocr", "page"))
        self.assertNotIn("snippet", observation)
        scan.assert_called_once()

    def test_numeric_table_can_end_with_an_explicit_reference_column(self):
        page = "Potwierdzenie przelewu\nKwota Data transakcji Numer referencyjny transakcji\n" \
               "\n3 942,55 PLN 08.02.2026 * TX/29512\nProwizja 8,20 PLN\nData wydruku 09.02.2026"
        value, diagnostics = extract_class(Document.from_pages(["Strona informacyjna", page]), self.classes, "przelew", [])
        self.assertEqual(value["przelew_bankowy"]["kwota"], 3942.55)
        self.assertEqual(value["przelew_bankowy"]["data_operacji"], "2026-02-08")
        for key in ("kwota", "data_operacji"):
            self.assertEqual(diagnostics["fields"]["przelew_bankowy." + key]["page"], 2)

    def test_flattened_operation_row_uses_price_and_separate_execution_cell(self):
        rows = ("Potwierdzenie przelewu", "Data wydruku: 2026-06-12", "Data Opis Kwota",
                "Data operacji - PRZELEW krajowy -5 280,44 PLN", "Data operacji -",
                "2026-06-10 Z rachunku: rachunek własny", "Data księgowania opis odbiorcy",
                "2026-06-11 Na rachunek: rachunek odbiorcy", "Prowizja 5,22 PLN")
        scan = Mock(return_value=[ScanView(1, "", rows), ScanView(1, "", rows)])
        primary = replace(Document.from_pages(["\n".join(rows[:4])]), bank_scan=scan)
        value, diagnostics = extract(primary, self.classes)
        self.assertEqual(value["przelew_bankowy"]["kwota"], 5280.44)
        self.assertEqual(value["przelew_bankowy"]["data_operacji"], "2026-06-10")
        self.assertEqual(diagnostics["fields"]["przelew_bankowy.data_operacji"]["page"], 1)
        scan.assert_called_once()

    def test_wrapped_booking_date_needs_the_operation_and_both_roles(self):
        rows = ("Data wydruku: 2026-08-03", "Data operacji PRZELEW krajowy",
                "Z rachunku: rachunek nadawcy", "Data księgowania dane odbiorcy",
                "2026-08-02", "Na rachunek: rachunek odbiorcy")
        self.assertIn((2, "2026-08-02"), view_evidence(rows)["data_operacji"])
        self.assertNotIn("data_operacji", view_evidence(rows[:-1]))
        self.assertNotIn("data_operacji", view_evidence(rows[:2] + rows[3:]))

    def test_wrapped_execution_label_requires_the_complete_role(self):
        self.assertEqual(view_evidence(("Data 2026-10-19", "wykonania")),
                         {"data_operacji": [(3, "2026-10-19")]})
        self.assertFalse(view_evidence(("Data 2026-10-19", "wydruku")))
        self.assertFalse(view_evidence(("Data 2026-02-31", "wykonania")))
        roles = ("Z rachunku: rachunek nadawcy", "Data księgowania: 2026-10-19",
                 "Na rachunek: rachunek odbiorcy")
        for row in ("Data operacji przelew: prowizja 95,12 PLN", "Data operacji przelew: 55,10 EUR"):
            self.assertNotIn("kwota", view_evidence(("Data Opis Kwota", row, *roles)))

    def test_completed_order_summary_uses_only_its_own_price_and_execution_date(self):
        rows = ("Status", "Wykonane", "Data wydruku 04 05 2026", "Dane zlecenia",
                "○ -2 301.28 PLN", "Tryb realizacj. zwykły", "Dala wykonania 03 05 2026",
                "Prowizja 14,20 PLN")
        doc = Document.from_pages(["Informacja dla klienta", "\n".join(rows)])
        value, diagnostics = extract_class(doc, self.classes, "przelew", [])
        self.assertEqual(value["przelew_bankowy"]["kwota"], 2301.28)
        self.assertEqual(value["przelew_bankowy"]["data_operacji"], "2026-05-03")
        for key in ("kwota", "data_operacji"):
            self.assertEqual(diagnostics["fields"]["przelew_bankowy." + key]["page"], 2)
        self.assertFalse(view_evidence(("Status Oczekujące", *rows[2:])))
        self.assertFalse(view_evidence(("Status Wykonane", *rows[2:6], "Planowana Dala wykonania 03 05 2026")))
        changed = (*rows[:4], "Prowizja 14,20 PLN", *rows[5:])
        self.assertEqual(view_evidence(changed), {"data_operacji": [(3, "2026-05-03")]})

    def test_alternate_class_does_not_discard_a_primary_amount_and_execution_date(self):
        scan = Mock(return_value=[ScanView(1, "Potwierdzenie przelewu\nRachunek odbiorcy: brak", ())])
        primary = replace(Document.from_pages(["Bank przelew\nStatus wykonane\nDane zlecenia\n"
                                               "○ 416,52 PLN\nTryb realizacji zwykły\nData wykonania 02 04 2026",
                                               "Kwota Data transakcji\n65,25 PLN 05.04.2026"]),
                          bank_scan=scan)
        value, diagnostics = extract(primary, self.classes)
        self.assertTrue(diagnostics["classification_from_ocr_layout"])
        self.assertEqual(value["przelew_bankowy"]["kwota"], 416.52)
        self.assertEqual(value["przelew_bankowy"]["data_operacji"], "2026-04-02")
        for key in ("kwota", "data_operacji"):
            observation = diagnostics["fields"]["przelew_bankowy." + key]
            self.assertEqual((observation["page"], observation["precision"]), (1, "page"))
        scan.assert_called_once()
