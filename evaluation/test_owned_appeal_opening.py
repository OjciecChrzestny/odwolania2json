"""Appeal-opening classification is supported by an actor and an owned filing."""
import unittest

from odwolania2json.model import Document, classify, load_classes


TITLE = "Pismo w postępowaniu"
HEADER = "Do Prezesa KIO\nOdwołująca: Firma Fikcyjna Jodła\nZnak postępowania: AA.19/2029"
DECLARATION = "Odwołująca składa niniejsze odwołanie od decyzji o odrzuceniu oferty."
RULE = "samodzielna_formuła_z_rolą_i_adresatem"


class OwnedAppealOpeningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def classify(self, *pages):
        return classify(Document.from_pages(pages), self.classes)

    def test_second_page_carries_the_filing_signal(self):
        result, signals = self.classify("Pierwsza strona pisma.", f"{TITLE}\n{HEADER}\n{DECLARATION}")
        self.assertEqual(result, "odwolanie")
        signal, = [signal for signal in signals if signal["rule"] == RULE]
        self.assertEqual(signal["page"], 2)

    def test_recipient_inside_the_filing_clause(self):
        body = "Wnosimy do Prezesa KIO niniejsze odwołanie wobec zaniechania odrzucenia oferty."
        header = "Odwołujący: Spółka Fikcyjna.\nNumer postępowania: AK-5/2029"
        self.assertEqual(self.classify(f"{TITLE}\n{header}\n{body}")[0], "odwolanie")

    def test_quotes_attachments_future_and_negation_do_not_gain_a_filing(self):
        docs = (
            f"{TITLE}\n{HEADER}\nZ pisma innego wykonawcy przytaczamy:\n{DECLARATION}",
            f"{TITLE}\n{HEADER}\nPrzytoczenie:\n{DECLARATION}",
            f"{TITLE}\n{HEADER}\n„\n{DECLARATION}\n”",
            f"ZAŁĄCZNIK: KOPIA OBCEGO PISMA\n{HEADER}\n{DECLARATION}",
            f"PROJEKT - ODWOŁANIE\n{HEADER}\n{DECLARATION}",
            f"POUCZENIE O PRAWIE WNIESIENIA ODWOŁANIA\n{HEADER}\n{DECLARATION}",
            f"{TITLE}\n{HEADER}\nOdwołująca jutro złoży odwołanie od decyzji.",
            f"{TITLE}\n{HEADER}\nWnosimy w imieniu wykonawcy projekt odwołania od decyzji.",
            f"{TITLE}\n{HEADER}\nW imieniu wykonawcy nie składamy odwołania od czynności.",
        )
        for text in docs:
            with self.subTest(text=text):
                self.assertEqual(self.classify(text)[0], "negative")

    def test_signals_from_different_pages_do_not_combine_for_the_new_rule(self):
        self.assertEqual(self.classify(f"{TITLE}\n{HEADER}", DECLARATION)[0], "negative")

    def test_opinion_about_the_subject_does_not_amount_to_filing(self):
        body = "Przedmiotem niniejszego odwołania jest decyzja o odrzuceniu oferty.\nTrwa przygotowanie stanowiska."
        self.assertEqual(self.classify(f"{TITLE}\n{HEADER}\n{body}")[0], "negative")
