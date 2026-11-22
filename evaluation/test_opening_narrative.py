"""Native synthetic counterexamples for independent appeal-opening classification."""
import unittest

from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


RECIPIENT = "Adresat: Prezes Krajowej Izby Odwoławczej"
REFERENCE = "Znak postępowania: PK-Z.45/2027"
ACT = "od decyzji o odrzuceniu oferty zamawiającego."
LEGAL = f"Na podstawie art. 513 pkt 1 ustawy Pzp niniejszym wnosimy odwołanie {ACT}"
SELF = f"Niniejszym Odwołująca składa odwołanie {ACT}"
INVERTED = "Od czynności Zamawiającego polegającej na wyborze oferty, wnosimy odwołanie."
RULE = "własne_wniesienie_z_jednoznacznym_adresatem"


def opening(clause, recipient=RECIPIENT, reference=REFERENCE):
    return "\n".join(("PISMO W POSTĘPOWANIU", recipient, reference, clause))


class OpeningNarrativeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def extract(self, *pages):
        return extract(Document.from_pages(pages), self.classes)

    def assert_negative(self, *pages):
        data, diagnostic = self.extract(*pages)
        self.assertIsNone(data)
        self.assertEqual(diagnostic["class"], "negative")

    def test_independent_filing_with_legal_basis_self_designation_or_inversion(self):
        paragraphs = (
            LEGAL, SELF, INVERTED,
            "Stosownie do art. 513 ust. 2 ustawy Pzp,\n"
            "składam niniejsze odwołanie wobec zaniechania oceny oferty.",
        )
        for clause in paragraphs:
            with self.subTest(clause=clause):
                data, diagnostic = self.extract("Pismo przewodnie.", opening(clause))
                self.assertEqual(diagnostic["class"], "odwolanie")
                self.assertIn("OdwolanieKIO", data)
                signal, = [s for s in diagnostic["signals"] if s["rule"] == RULE]
                self.assertEqual(signal["page"], 2)

    def test_address_and_case_identify_the_same_page_as_the_operative_clause(self):
        self.assert_negative(opening(LEGAL, recipient="Do Zamawiającego"))
        self.assert_negative(opening(LEGAL, reference=""))
        self.assert_negative(opening("", recipient=RECIPIENT), LEGAL)
        self.assert_negative(opening(LEGAL, recipient="Kopia dla Prezesa Krajowej Izby Odwoławczej"))

    def test_quoted_project_future_and_negative_statements_are_not_filings(self):
        examples = (
            f"Treść przytoczonego pisma:\n{LEGAL}",
            f"Poniżej przytaczamy zdanie z pisma:\n{SELF}",
            f"Cytat z pisma:\n{INVERTED}",
            f"„\n{LEGAL}\n”",
            f"> {LEGAL}",
            "Na podstawie art. 513 ustawy Pzp zamierzamy wnieść odwołanie od czynności zamawiającego.",
            "Na podstawie art. 513 ustawy Pzp nie wnoszę odwołania od czynności zamawiającego.",
            "Od czynności Zamawiającego polegającej na wyborze oferty, nie wnosimy odwołania.",
            "Niniejszym Odwołująca informuje, że jutro złoży odwołanie od czynności zamawiającego.",
            "Niniejszym Zamawiający wnosi o oddalenie odwołania od czynności zamawiającego.",
        )
        for clause in examples:
            with self.subTest(clause=clause):
                self.assert_negative(opening(clause))

    def test_response_and_discontinuance_order_with_quoted_legacy_signals(self):
        copied = "\n".join((
            "Krajowa Izba Odwoławcza", "Zamawiający: Jednostka fikcyjna",
            "ODWOŁANIE", REFERENCE, f"Przytaczamy pismo wykonawcy:\n{LEGAL}",
        ))
        headings = (
            "ODPOWIEDŹ UCZESTNIKA POSTĘPOWANIA NA ODWOŁANIE W SPRAWIE PK-Z.45/2027",
            "POSTANOWIENIE O UMORZENIU POSTĘPOWANIA",
        )
        for heading in headings:
            with self.subTest(heading=heading):
                self.assert_negative(f"{heading}\n{copied}")

    def test_explicit_quotation_does_not_veto_a_separate_filing(self):
        header = "\n".join(("Krajowa Izba Odwoławcza", "Odwołujący: Fikcyjny wykonawca",
                            "Zamawiający: Fikcyjna jednostka", "ODWOŁANIE", REFERENCE))
        own = "Działając w imieniu wykonawcy, wnoszę odwołanie od czynności zamawiającego."
        quotation = f"Cytat:\n„{SELF}”"
        documents = (
            f"{header}\n{quotation}\n{own}",
            f"{header}\n{own}\n{quotation}",
            f"{header}\nCytat:\n{SELF}\nKoniec cytatu.\n{own}",
            f"{header}\n{quotation}\n" + "Dalsza treść wprowadzająca. " * 15 + f"\n{own}",
            f"{header}\n{quotation}\n{LEGAL}",
        )
        for index, text in enumerate(documents):
            with self.subTest(index=index):
                data, diagnostic = self.extract(text)
                self.assertEqual(diagnostic["class"], "odwolanie")
                self.assertIn("OdwolanieKIO", data)

    def test_quotation_with_only_a_copied_filing_remains_negative(self):
        header = "\n".join(("Krajowa Izba Odwoławcza", "Odwołujący: Fikcyjny wykonawca",
                            "Zamawiający: Fikcyjna jednostka", "ODWOŁANIE", REFERENCE))
        copied = "Działając w imieniu wykonawcy, wnoszę odwołanie od czynności zamawiającego."
        for quote in (f"„{copied}”", f"„\n{copied}\n”", copied, f"{LEGAL}\nKoniec cytatu."):
            with self.subTest(quote=quote):
                self.assert_negative(f"{header}\nCytat:\n{quote}")

        long_quote = f"„Fragment innego pisma.”\n{copied}\nKoniec cytatu."
        self.assert_negative(f"{header}\nCytat:\n{long_quote}")
        self.assertEqual(self.extract(f"{header}\nCytat:\n{long_quote}\n{LEGAL}")[1]["class"], "odwolanie")

    def test_action_fallback_uses_explicit_subject_and_one_physical_page(self):
        from odwolania2json.filing_subject import select_filing_subject
        from odwolania2json.legal import Fragment

        config = self.classes["odwolanie"]
        samples = (
            ("treści Specyfikacji Warunków Zamówienia (SWZ) opublikowanej w celu prowadzenia postępowania", 4),
            ("projektowanych postanowień umowy opisanej w załączniku", 12),
            ("zmiany treści SWZ dokonanej w ubiegłym tygodniu", 5),
        )
        for text, reason in samples:
            with self.subTest(reason=reason):
                doc = Document.from_pages(("To jest pismo przewodnie.", text))
                subject = select_filing_subject(doc, config, Fragment(text, doc.starts[1][0]))
                self.assertEqual((subject.reason_id, subject.page), (reason, 2))
                self.assertEqual(subject.description, config["reasons"]["descriptions"][str(reason)])
                self.assertTrue(text.startswith(doc.text[subject.offset:subject.end]))

    def test_first_title_item_has_precedence_and_copied_text_is_ignored(self):
        from odwolania2json.filing_subject import select_filing_subject

        config = self.classes["odwolanie"]
        title = "Krajowa Izba Odwoławcza\nODWOŁANIE\nod czynności i zaniechań Zamawiającego\n\nwobec: .\n"
        case = title + "1. modyfikacji treści SWZ;\n2. projektowanych postanowień umowy."
        positive = select_filing_subject(Document.from_pages((case,)), config)
        self.assertEqual((positive.reason_id, positive.page), (5, 1))
        self.assertEqual(case[positive.offset:positive.end], "modyfikacji treści SWZ")
        for text in (
            "Cytat:\n" + case, "„\n" + case + "\n”",
            title + "2. projektowanych postanowień umowy.",
            title + "1. wezwania do uzupełnienia dokumentów;\n2. modyfikacji treści SWZ.",
            title + "1. treści SWZ.\nŻądania:\n1. modyfikacji treści SWZ.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(select_filing_subject(Document.from_pages((text,)), config))

    def test_fallback_prefers_screened_declaration_and_does_not_choose_a_later_request(self):
        from odwolania2json.filing_subject import select_filing_subject
        from odwolania2json.legal import Fragment

        config = self.classes["odwolanie"]
        for phrase in (
            "zaniechania modyfikacji treści SWZ",
            "treści Specyfikacji Warunków Zamówienia (SWZ)",
            "wyboru oferty; następnie żądam modyfikacji treści SWZ",
            "naruszenia ustawy; projektowanych postanowień umowy",
        ):
            doc = Document.from_pages((phrase,))
            self.assertIsNone(select_filing_subject(doc, config, Fragment(phrase)))
        pages = ("treści Specyfikacji Warunków", "Zamówienia (SWZ) opublikowanej")
        doc = Document.from_pages(pages)
        self.assertIsNone(select_filing_subject(doc, config, Fragment(doc.text)))
        self.assertIsNone(select_filing_subject(doc, config, Fragment("modyfikacji treści SWZ")))
