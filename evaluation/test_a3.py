"""Regresje zakresu pełnomocnictwa i pierwszej czynności, na fikcyjnej treści."""
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter
from odwolania2json.extract import extract, read_pdf
from odwolania2json.model import Document, load_classes
from test_baseline_a import write_pdf


GRANT = ("Alfa sp. z o.o., ul. Testowa 4, NIP 0001234567, niniejszym upoważniam "
         "adw. Anna Nowak do reprezentowania spółki przed Krajową Izbą Odwoławczą.")
APPEAL = ("Krajowa Izba Odwoławcza\nOdwołujący: Fikcyjna spółka\n"
          "Zamawiający: Fikcyjna gmina\nODWOŁANIE")


class MandateTest(unittest.TestCase):
    def setUp(self):
        self.classes = load_classes()

    def test_title_and_operating_clause_give_the_same_parties_behind_a_cover(self):
        expected, _ = extract(Document.from_pages(["PEŁNOMOCNICTWO\n" + GRANT]), self.classes)
        self.assertEqual(expected["mocodawca"][0]["data"]["nazwa"], "Alfa sp. z o.o.")
        self.assertEqual(expected["mocodawca"][0]["data"]["nip"], "0001234567")
        self.assertEqual(expected["pelnomocnicy"], [{"imie_nazwisko": "Anna Nowak", "pesel": None}])
        for verb in ("niniejszym upoważniam", "umocowuję"):
            mandate = "PEŁNOMOCNICTWO DO REPREZENTACJI\n" + GRANT.replace("niniejszym upoważniam", verb)
            for pages in ([mandate], ["Pismo przewodnie\nAdresat: inny podmiot.", "Karta obiegu", mandate]):
                with self.subTest(verb=verb, page=len(pages)):
                    value, entry = extract(Document.from_pages(pages), self.classes)
                    self.assertEqual(value, expected)
                    self.assertEqual({s["page"] for s in entry["signals"]}, {len(pages)})
                    self.assertEqual({s["page"] for s in entry["fields"].values()}, {len(pages)})

    def test_notice_list_quoted_form_and_signals_on_separate_pages(self):
        title = "PEŁNOMOCNICTWO DO REPREZENTACJI"
        for pages in (["Wezwanie do uzupełnienia dokumentów\nProszę przedłożyć pełnomocnictwo."],
                      ["Wykaz załączników\n" + title],
                      ["Instrukcja wypełnienia formularza\n" + title + "\n" + GRANT],
                      ["Pismo przewodnie", title, GRANT],
                      ["Wykaz załączników", title + "\n" + GRANT]):
            with self.subTest(pages=len(pages)):
                value, entry = extract(Document.from_pages(pages), self.classes)
                self.assertIsNone(value)
                self.assertEqual(entry["class"], "negative")
        _, appeal = extract(Document.from_pages([APPEAL, title + "\n" + GRANT]), self.classes)
        self.assertEqual(appeal["class"], "odwolanie")

    def test_mixed_pdf_requests_ocr_only_for_unreadable_continuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cover, second, mixed = root/"cover.pdf", root/"sheet.pdf", root/"bank.pdf"
            write_pdf(cover, "PISMO PRZEWODNIE")
            write_pdf(second, "Karta obiegu dokumentu")
            pdf = PdfWriter()
            pdf.append(cover)
            pdf.append(second)
            pdf.add_blank_page(width=600, height=800)
            pdf.write(mixed)
            calls = []

            def scanned(path, limit, *, start=0):
                calls.append((path, start, limit))
                return [(2, "PEŁNOMOCNICTWO DO REPREZENTACJI\n" + GRANT)]

            doc, pages = read_pdf(mixed, scanned, classes=self.classes)
            self.assertEqual(calls, [(mixed, 2, 3)])
            self.assertEqual(pages, [3])
            value, record = extract(doc, self.classes)
            self.assertEqual(record["class"], "pelnomocnictwo")
            self.assertEqual(value["pelnomocnicy"][0]["imie_nazwisko"], "Anna Nowak")


class FirstClaimTest(unittest.TestCase):
    def assert_reason(self, first, expected, *, second="Wybór oferty", date=None, fallback=False):
        pages = [APPEAL, first + "\nZarzut II: " + second]
        config = load_classes()
        out, diag = extract(Document.from_pages(pages), config)
        action = out["OdwolanieKIO"]
        self.assertEqual(action["czynnosc_powod_id"], expected)
        self.assertEqual(action["czynnosc_opis"], config["odwolanie"]["reasons"]["descriptions"][str(expected)])
        self.assertEqual(action["czynnosc_dzien"], date)
        self.assertEqual(diag["first_allegation"]["fallback"], fallback)
        self.assertEqual(diag["first_allegation"]["page"], 2)

    def test_explicit_decision_outweighs_earlier_background_and_excluded_date(self):
        self.assert_reason("Zarzut I: Nie kwestionujemy wyboru oferty w dniu 2 stycznia 2026 r. "
                           "Kwestionujemy wykluczenie wykonawcy w dniu 3 stycznia 2026 r.", 3, date="2026-01-03")
        self.assert_reason("Zarzut pierwszy: Nie kwestionujemy wyboru oferty, "
                           "natomiast kwestionujemy zaniechanie wykluczenia wykonawcy.", 8)
        self.assert_reason("Zarzut I: Nie zaskarżamy wyboru oferty.", 11, fallback=True)
        self.assert_reason("Zarzut nr1: W tle był wybór oferty. " + "Okoliczności prawne. " * 14
                           + "Kwestionujemy odrzucenie oferty.", 1)

    def test_paraphrase_and_each_act_versus_omission(self):
        for phrase, reason in (
                ("Zamawiający pozbawił wykonawcę prawa dalszego udziału w postępowaniu.", 3),
                ("Zamawiający nie pozbawił wykonawcy prawa dalszego udziału w postępowaniu.", 8),
                ("Odrzucenie oferty.", 1), ("Zaniechanie odrzucenia oferty.", 7),
                ("Wykluczenie wykonawcy.", 3), ("Zaniechanie wykluczenia wykonawcy.", 8),
                ("Unieważnienie postępowania.", 9), ("Zaniechanie unieważnienia postępowania.", 10)):
            with self.subTest(phrase=phrase):
                self.assert_reason("Zarzut 1: " + phrase, reason)

    def test_first_claim_can_follow_a_long_introduction(self):
        pages = [APPEAL, "Tło postępowania. " * 580, "Zarzut I: Kwestionujemy odrzucenie oferty."]
        out, diagnostic = extract(Document.from_pages(pages), load_classes())
        self.assertEqual(out["OdwolanieKIO"]["czynnosc_powod_id"], 1)
        self.assertEqual(diagnostic["first_allegation"]["page"], 3)
        self.assertFalse(diagnostic["first_allegation"]["fallback"])

    def test_later_list_and_justification_cannot_override_first_claim(self):
        self.assert_reason("Zarzut I: Wykluczenie wykonawcy.", 3,
                           second="Zarzucamy:\n1) odrzucenie oferty.\n2) wybór oferty.")
        self.assert_reason("Zarzuty:\n1) zaniechanie odrzucenia oferty.\n2) wybór oferty.", 7)
        self.assert_reason("Zarzut pierwszy: Niewskazana w słowniku czynność.\n"
                           "Uzasadnienie\nKwestionujemy wybór oferty.", 11, fallback=True)

    def test_list_under_only_second_claim_cannot_supply_the_first(self):
        out, diagnostic = extract(Document.from_pages([APPEAL,
            "Zarzut II: Inna czynność.\nZarzucamy:\n1) odrzucenie oferty."]), load_classes())
        self.assertEqual(out["OdwolanieKIO"]["czynnosc_powod_id"], 11)
        self.assertTrue(diagnostic["first_allegation"]["fallback"])
