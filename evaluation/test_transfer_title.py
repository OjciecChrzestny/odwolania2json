"""Transfer-title boundaries exercised through normal extraction."""
from copy import deepcopy
import unittest

from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


class TransferTitleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def parse(self, *lines, next_page=None, classes=None):
        page = "\n".join(("POTWIERDZENIE PRZELEWU", "Data operacji: 2026-05-07", "Kwota: 94,10 PLN", *lines))
        doc = Document.from_pages([page, next_page] if next_page else [page])
        result, diagnostic = extract(doc, classes or self.classes)
        return result["przelew_bankowy"], diagnostic["fields"]

    def test_single_line_with_punctuation_and_inline_status(self):
        bank, evidence = self.parse("Tytul operacji: FV/09 – Część A (I), 7.50 PLN. | Status: zrealizowano",
                                    "Treść innego pola", "Numer transakcji: 000123")
        self.assertEqual(bank, {
            "data_operacji": "2026-05-07", "kwota": 94.1, "tytul": "FV/09 – Część A (I), 7.50 PLN.",
            "numer_transakcji": "000123", "z_rachunku": None, "na_rachunek": None,
        })
        self.assertEqual(evidence["przelew_bankowy.tytul"]["page"], 1)
        tight, _ = self.parse("Tytuł: FV/09|Status: zrealizowano")
        self.assertEqual(tight["tytul"], "FV/09")

    def test_wrapped_value_ends_at_footer_or_next_field(self):
        for end in ("Data księgowania 2026-05-08", "Data nadania: 2026-05-08",
                    "Bank Nadwiślański S.A.",
                    "Dokument wygenerowany elektronicznie."):
            with self.subTest(end=end):
                bank, _ = self.parse("Szczegóły płatności", "", "Za wykonanie usługi",
                                     "w kwietniu, FV 4/2026", end, "Informacje o banku")
                self.assertEqual(bank["tytul"], "Za wykonanie usługi w kwietniu, FV 4/2026")

    def test_wrapping_across_ocr_blank_requires_a_bounded_continuation(self):
        for continuation in ("i montaż na miejscu", "PO.23/III RT93457"):
            with self.subTest(continuation=continuation):
                bank, _ = self.parse("Tytuł: Zamówienie na dostawę", "", continuation, "",
                                     "Numer referencyjny: 000123")
                self.assertEqual(bank["tytul"], f"Zamówienie na dostawę {continuation}")
        bank, _ = self.parse("Tytuł: Zamówienie na dostawę", "", "i montaż na miejscu")
        self.assertEqual(bank["tytul"], "Zamówienie na dostawę")

    def test_field_word_can_start_the_value_after_explicit_label(self):
        bank, _ = self.parse("Tytuł: Kwota wykorzystana przy zamówieniu", "Status: wykonano")
        self.assertEqual(bank["tytul"], "Kwota wykorzystana przy zamówieniu")

    def test_wrapped_quoted_title_ends_at_closing_quote(self):
        bank, _ = self.parse("Tytułem „Usługa – etap I", "i II”. Dodatkowa treść", "Informacje")
        self.assertEqual(bank["tytul"], "Usługa – etap I i II")

    def test_title_pipes_without_table_evidence_are_literal(self):
        bank, _ = self.parse("Tytuł: FV AB/10 | Etap II")
        self.assertEqual(bank["tytul"], "FV AB/10 | Etap II")

    def test_table_reads_its_column_and_stops_at_new_record(self):
        bank, _ = self.parse("Data operacji | Tytuł przelewu | Kwota",
                             "2026-05-07 | Łącze – etap I | 94,10 PLN", " | maj (FV/01) | ",
                             "2026-05-08 | Kolejna transakcja | 55,00 PLN")
        self.assertEqual(bank["tytul"], "Łącze – etap I maj (FV/01)")

    def test_empty_title_never_copies_next_field_footer_or_page(self):
        for rows in (("Tytuł:", "", "Numer operacji 000123"),
                     ("Tytuł: Status: wykonano", "Dodatkowa informacja"),
                     ("Tytuł", "Wydruk z systemu bankowości elektronicznej"),
                     ("Tytuł: ---", "Wydruk z systemu bankowości elektronicznej"),
                     ("Data operacji | Tytuł | Kwota", "2026-05-07 | | 94,10 PLN"),
                     ("Tytuł:",)):
            with self.subTest(rows=rows):
                bank, evidence = self.parse(*rows, next_page="Tekst z kolejnej strony")
                self.assertIsNone(bank["tytul"])
                self.assertNotIn("przelew_bankowy.tytul", evidence)

    def test_specific_label_has_priority_over_payment_section(self):
        bank, _ = self.parse("Payment details", "Title: Materials", "Transaction status: Posted")
        self.assertEqual(bank["tytul"], "Materials")

    def test_operation_description_is_not_a_title(self):
        bank, _ = self.parse("Opis kodu operacji PRZELEW SYSTEMOWY", "Opis operacji: Przelew wychodzący")
        self.assertIsNone(bank["tytul"])
        bank, _ = self.parse("Opis operacji: Przelew wychodzący", "Tytuł: FV-6")
        self.assertEqual(bank["tytul"], "FV-6")
        bank, _ = self.parse("Opis: Zaliczka na materiały", "", "Informacja z kolejnego akapitu")
        self.assertEqual(bank["tytul"], "Zaliczka na materiały")

    def test_custom_title_rule_still_uses_generic_extraction(self):
        classes = deepcopy(self.classes)
        classes["przelew"]["fields"]["przelew_bankowy.tytul"] = [
            {"name": "etykieta_użytkownika", "pattern": r"^Memo: ([^\n]+)$", "operation": "text"}
        ]
        bank, evidence = self.parse("Memo: Zapłata", "Tytuł: Inna wartość", classes=classes)
        self.assertEqual(bank["tytul"], "Zapłata")
        self.assertEqual(evidence["przelew_bankowy.tytul"]["rule"], "etykieta_użytkownika")
