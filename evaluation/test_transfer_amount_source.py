"""Operation-context regression tests for transfer amount evidence."""
from unittest import TestCase

from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes
from odwolania2json.review import review_details


AMOUNT = "przelew_bankowy.kwota"
COVER = "POTWIERDZENIE PRZELEWU\nNumer transakcji: OP-7391\nData operacji: 2026-03-12"


class TransferAmountSourceTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def extract(self, *pages):
        doc = Document.from_pages(pages)
        value, record = extract(doc, self.classes)
        self.assertEqual(record["class"], "przelew")
        review = review_details(doc, record, value, False)
        return value["przelew_bankowy"]["kwota"], review["fields"][AMOUNT], review["review"]

    def exact(self, result, value, page, snippet, *, linked=True):
        number, proof, _ = result
        self.assertEqual(number, value)
        self.assertEqual(
            (proof["precision"], proof["page"], proof["snippet"], proof["source"]),
            ("snippet", page, snippet, "text"),
        )
        self.assertEqual(proof["span"]["end"] - proof["span"]["start"], len(snippet))
        self.assertEqual(proof["rule"], "kwota_powiazana_z_id_operacji" if linked else "kwota_operacji")

    def unresolved(self, result, value):
        amount, proof, review = result
        self.assertEqual(amount, value)
        self.assertEqual((proof["kind"], proof["precision"], proof["page"]), ("conflict", "unavailable", None))
        self.assertFalse({"snippet", "span", "context"} & proof.keys())
        self.assertEqual(review["status"], "review_required")
        self.assertIn({"code": "field_evidence_conflict", "field": AMOUNT}, review["reasons"])

    def test_same_value_on_another_page_does_not_prove_current_operation(self):
        old = "Termin rozliczenia\nIdentyfikator transakcji: ARCH-65\nKwota: 1 234,56 PLN"
        current = "Operacja OP-7391\nKwota: 1 234,56 PLN\nPrzelew wychodzący"
        self.exact(self.extract(COVER, old, "Informacje porządkowe", current),
                   1234.56, 4, "1 234,56")

    def test_different_earlier_amount_does_not_replace_current_amount(self):
        old = "Numer przelewu: ARCH-654\nKwota: 906,77 PLN"
        current = "Szczegóły transakcji OP-7391\nKwota: 124,11 PLN\nRachunek odbiorcy: 00"
        self.exact(self.extract(COVER, "Załączniki", old, current),
                   124.11, 4, "124,11")

    def test_two_sections_on_same_page_can_bind_reference_after_value(self):
        current = "Kwota: 304,09 PLN\nIdentyfikator operacji: OP-7391\nZ rachunku: 00"
        old = "Numer przelewu: ARCH-22\nKwota: 906,77 PLN"
        self.exact(self.extract(COVER, old + "\n\n" + current), 304.09, 2, "304,09")

    def test_one_amount_and_equal_commission_keep_the_original_capture(self):
        single = "Kwota: 211,09 PLN"
        self.exact(self.extract(COVER, "Prowizja: 211,09 PLN", single),
                   211.09, 3, "211,09", linked=False)

    def test_duplicates_without_reference_alignment_require_review(self):
        other = "Kwota: 72,42 PLN\nPrzelew wychodzący"
        near_miss = "Operacja OP-73910\nKwota: 72,42 PLN\nRachunek odbiorcy: 00"
        self.unresolved(self.extract(COVER, other, near_miss), 72.42)

    def test_matching_heading_alone_does_not_identify_a_weak_block(self):
        self.unresolved(self.extract(COVER, "Kwota: 72,42 PLN\nRachunek odbiorcy: 00",
                                     "Operacja OP-7391\nKwota: 72,42 PLN"), 72.42)

    def test_one_amount_explicitly_assigned_to_another_operation_is_provisional(self):
        self.unresolved(self.extract(COVER, "Numer operacji: ARCH-15\nKwota: 72,42 PLN"), 72.42)

    def test_conflicting_references_in_one_block_do_not_prove_amount(self):
        other = "Kwota: 72,42 PLN"
        uncertain = "Operacja OP-7391\nNumer operacji: ARCH-15\nKwota: 72,42 PLN\nPrzelew wychodzący"
        self.unresolved(self.extract(COVER, other, uncertain), 72.42)

    def test_column_value_can_be_bound_to_the_current_section(self):
        old = "Numer transakcji: ARCH-15\nKwota: 72,42 PLN"
        current = "Numer transakcji: OP-7391\nKwota Data operacji\n65,01 PLN 2026-03-12"
        self.exact(self.extract(COVER, old, current), 65.01, 3, "65,01")

    def test_reference_mentioned_in_title_is_not_the_local_operation_heading(self):
        unrelated = "Tytuł operacja OP-7391\nKwota: 72,42 PLN\nPrzelew wychodzący"
        self.unresolved(self.extract(COVER, "Kwota: 72,42 PLN", unrelated), 72.42)
