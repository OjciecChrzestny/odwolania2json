"""Synthetic checks for the optional own-opening subject fallback."""
import unittest

from odwolania2json.__main__ import _DEFAULT_EXTRACT_DOCUMENT
from odwolania2json.filing_subject import select_opening_subject
from odwolania2json.model import Document, load_classes


HEADER = "Krajowa Izba Odwoławcza\nOdwołujący: Fikcyjna spółka\nODWOŁANIE\n"
SELECTION = "Odwołujący zaskarża wybór oferty."
MODIFICATION = "Przedmiotem niniejszego odwołania jest modyfikacja treści SWZ."


class FilingSubjectOpeningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()
        cls.config = cls.classes["odwolanie"]

    def test_opening_identifies_configured_action_on_its_actual_page(self):
        examples = (
            (SELECTION, 2),
            (MODIFICATION, 5),
            ("Składam odwołanie od projektowanych postanowień umowy.", 12),
            ("Działając w imieniu spółki,\nskładam odwołanie od zaniechania unieważnienia postępowania.", 10),
        )
        for raw, expected in examples:
            with self.subTest(raw=raw):
                doc = Document.from_pages((HEADER, raw))
                witness = select_opening_subject(doc, self.config)
                self.assertEqual((witness.reason_id, witness.page), (expected, 2))
                self.assertEqual(witness.description, self.config["reasons"]["descriptions"][str(expected)])
                excerpt = doc.text[witness.offset:witness.end]
                self.assertIn(excerpt, raw)
                self.assertNotIn("\f", excerpt)

    def test_foreign_excerpt_and_later_requests_do_not_choose_an_id(self):
        examples = (
            f"Cytat:\n{SELECTION}",
            f"„\n{SELECTION}\n”",
            f"Cytat:\n„Fragment.”\n{SELECTION}\nKoniec cytatu.",
            f"Uzasadnienie:\n{SELECTION}",
            f"Żądania:\n{MODIFICATION}",
            "Działając w imieniu spółki nie składam odwołania od wyboru oferty.",
            "Przedmiotem niniejszego odwołania jest naruszenie przepisu o zmianie treści SWZ.",
            "Odwołujący zaskarża wykluczenie odpowiedzialności cywilnej.",
            "Odwołujący zaskarża zaniechanie odrzucenia wniosku.",
            "Odwołujący zaskarża zaniechanie unieważnienia umowy.",
            "Odwołujący zaskarża zaniechanie wykluczenia odpowiedzialności cywilnej.",
            "Odwołujący zaskarża udzielenie wyjaśnień do protokołu.",
            f"Z pisma innego wykonawcy przytaczamy:\n{SELECTION}",
            f"Odwołujący zaskarża wysokość opłaty.\n{SELECTION}",
            "Odwołujący zaskarża zaniechanie zmiany wymogów dotyczących wykluczenia wykonawcy.",
        )
        for raw in examples:
            with self.subTest(raw=raw):
                self.assertIsNone(select_opening_subject(Document.from_pages((HEADER + raw,)), self.config))
        copied = Document.from_pages(("CYTAT Z PISMA:\n" + HEADER + SELECTION,))
        self.assertIsNone(select_opening_subject(copied, self.config))

    def test_explicit_end_of_quote_allows_a_distinct_own_clause(self):
        raw = f"{HEADER}Cytat:\n„Fragment.”\n{SELECTION}\nKoniec cytatu.\n{MODIFICATION}"
        witness = select_opening_subject(Document.from_pages((raw,)), self.config)
        self.assertEqual(witness.reason_id, 5)

    def test_first_owned_nominal_clause_uses_the_actual_specification(self):
        letterhead = "Do Prezesa KIO\nOdwołująca: Laboratorium Szron\n"
        clause = ("Przedmiotem niniejszego odwołania jest treść specyfikacji warunków "
                  "zamówienia udostępnionej w witrynie zamawiającego.\n"
                  "W dalszej części powołuję projektowane postanowienia umowy.")
        doc = Document.from_pages((letterhead + "ODWOŁANIE\n", clause))
        witness = select_opening_subject(doc, self.config)
        self.assertEqual((witness.reason_id, witness.page), (4, 2))
        self.assertEqual(doc.text[witness.offset:witness.end],
                         "treść specyfikacji warunków zamówienia udostępnionej")

    def test_other_speakers_and_incomplete_letterheads_leave_the_action_unresolved(self):
        examples = (
            (HEADER, "Poniżej podano model odpowiedzi na ćwiczenie.\n" + SELECTION),
            (HEADER, "Organizator zreferował cudzą wersję zdarzeń.\n" + SELECTION),
            (HEADER, "Nie podzielam poniższego stanowiska.\n" + SELECTION),
            (HEADER.replace("ODWOŁANIE", "Projekt odwołania\nODWOŁANIE"), SELECTION),
            (HEADER.replace("Krajowa Izba Odwoławcza\n", ""), SELECTION),
            (HEADER, "Tekst drugiej części stanowi osobny wzór pisma.", HEADER + SELECTION),
            (HEADER, "Składam odwołanie od treść specyfikacji warunków zamówienia opublikowanej."),
        )
        for pages in examples:
            with self.subTest(pages=pages):
                self.assertIsNone(select_opening_subject(Document.from_pages(pages), self.config))

    def test_institution_named_in_editorial_prose_is_not_the_addressee(self):
        heading = HEADER.replace("Krajowa Izba Odwoławcza\n",
                                 "Krajowa Izba Odwoławcza pokazuje przykład pisma.\n")
        doc = Document.from_pages((heading, "Składam odwołanie od projektowanych postanowień umowy."))
        value, trace = _DEFAULT_EXTRACT_DOCUMENT(doc, self.classes)
        self.assertEqual(value["OdwolanieKIO"]["czynnosc_powod_id"], 11)
        self.assertTrue(trace["first_allegation"]["fallback"])

    def test_intro_and_subject_must_share_a_physical_page(self):
        doc = Document.from_pages((HEADER + "Przedmiotem niniejszego odwołania jest", "modyfikacja treści SWZ."))
        self.assertIsNone(select_opening_subject(doc, self.config))

    def test_normal_entry_point_preserves_the_already_decided_pair(self):
        raw = HEADER + "Zarzut I: Kwestionuję wybór oferty.\nŻądania:\n" + MODIFICATION
        value, evidence = _DEFAULT_EXTRACT_DOCUMENT(Document.from_pages((raw,)), self.classes)
        self.assertEqual(value["OdwolanieKIO"]["czynnosc_powod_id"], 2)
        self.assertEqual(evidence["first_allegation"]["rule"], "pierwszy_numerowany_zarzut")
        self.assertFalse(evidence["first_allegation"]["fallback"])
