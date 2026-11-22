"""Classification of a filed procurement appeal and similar procedural texts."""
import unittest

from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


ADDRESSEE = "Do Prezesa Krajowej Izby Odwoławczej"
CASE = "Numer postępowania: PZ.17/2025"
FILING = "Niniejszym wnosimy odwołanie od czynności Zamawiającego polegającej na wyborze oferty."
LEGACY_CUES = "Krajowa Izba Odwoławcza\nZamawiający: Jednostka Przykładowa\nODWOŁANIE"
RULE = "wniesienie_odwołania"


class FiledAppealClassTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def parse(self, *pages):
        return extract(Document.from_pages(list(pages)), self.classes)

    def assert_negative(self, *pages):
        data, report = self.parse(*pages)
        self.assertIsNone(data)
        self.assertEqual(report["class"], "negative")

    def assert_filed(self, pages, page):
        data, report = self.parse(*pages)
        self.assertEqual(report["class"], "odwolanie")
        self.assertIn("OdwolanieKIO", data)
        [signal] = [entry for entry in report["signals"] if entry["rule"] == RULE]
        self.assertEqual(signal["page"], page)
        self.assertCountEqual(signal["criteria"],
                              ("formuła_poza_cytatem", "adresat_lub_strona", "kontekst_zamówienia"))

    def test_performative_with_addressee_and_case_without_title(self):
        self.assert_filed(["\n".join((ADDRESSEE, CASE, FILING))], 1)

    def test_party_as_alternative_evidence_on_second_page(self):
        appeal = "\n".join((
            "Wykonawca: Podmiot Przykładowy",
            "Znak postępowania: PZ.17/2025",
            "Działając w imieniu wykonawcy,",
            "składam odwołanie wobec zaniechania oceny oferty.",
            "Wyrok dotyczący innej sprawy przywołuję w uzasadnieniu.",
        ))
        self.assert_filed(["PISMO PRZEWODNIE", appeal], 2)

    def test_case_and_addressee_are_independent_requirements(self):
        self.assert_negative("\n".join((ADDRESSEE, FILING)))
        self.assert_negative("\n".join((CASE, FILING)))
        self.assert_negative("\n".join((ADDRESSEE, CASE)), FILING)

    def test_kio_judgment_and_order_are_negative(self):
        for heading in ("WYROK", "POSTANOWIENIE KRAJOWEJ IZBY ODWOŁAWCZEJ"):
            with self.subTest(heading=heading):
                self.assert_negative(f"Sygn. akt KIO 19/25\n{heading}\n{LEGACY_CUES}\n{CASE}\n{FILING}")

    def test_instruction_is_negative_even_with_filing_example(self):
        self.assert_negative(f"POUCZENIE O PRAWIE WNIESIENIA ODWOŁANIA\n{LEGACY_CUES}\n{CASE}\n{FILING}")

    def test_quotation_with_matching_parties_is_negative(self):
        context = f"Krajowa Izba Odwoławcza\nZamawiający: Jednostka Przykładowa\n{CASE}"
        self.assert_negative(f'{context}\nPrzytoczono: „wnoszę odwołanie od czynności Zamawiającego”.')
        self.assert_negative(f'{context}\nPrzytoczono: „\n{FILING}\n”')
        self.assert_negative(f'{context}\n> {FILING}')

    def test_entire_quoted_appeal_is_negative_even_with_legacy_cues(self):
        self.assert_negative(f"„\n{LEGACY_CUES}\n{CASE}\n{FILING}\n”")
        self.assert_negative(f"CYTAT Z ODWOŁANIA:\n{LEGACY_CUES}\n{CASE}\n{FILING}")

    def test_template_is_negative(self):
        self.assert_negative(f"WZÓR ODWOŁANIA\n{LEGACY_CUES}\n{CASE}\n{FILING}")

    def test_draft_is_negative(self):
        self.assert_negative(f"PROJEKT ODWOŁANIA\n{LEGACY_CUES}\n{CASE}\n{FILING}")

    def test_demand_in_another_letter_is_negative(self):
        self.assert_negative(f"ODPOWIEDŹ NA ODWOŁANIE\n{LEGACY_CUES}\n{CASE}\n{FILING}")
        self.assert_negative(f"{ADDRESSEE}\n{CASE}\nWnoszę o oddalenie odwołania.")
        self.assert_negative(f"{ADDRESSEE}\n{CASE}\nSkładam wniosek o zmianę warunków zamówienia.")
