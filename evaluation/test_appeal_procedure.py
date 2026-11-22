import unittest

from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


COVER = (
    "Łomża, 18 czerwca 2026 r.\n"
    "Krajowa Izba Odwoławcza\n"
    "Odwołujący: Przykładowy wykonawca sp. z o.o., KRS 0000789012\n"
    "Zamawiający: Fikcyjna gmina, NIP 0000065432\n"
    "ODWOŁANIE"
)


class AppealProcedureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def get_appeal(self, *pages):
        value, evidence = extract(Document.from_pages([COVER, *pages]), self.classes)
        self.assertEqual(evidence["class"], "odwolanie")
        return value, evidence["fields"]

    def test_act_date_precedes_notification_and_other_dates(self):
        output, proof = self.get_appeal(
            "Wnoszę odwołanie od decyzji o odrzuceniu oferty z dnia 10 czerwca 2026 r., "
            "o której zamawiający poinformował w dniu 12 czerwca 2026 r.\n"
            "Wnoszę o dokonanie ponownej oceny w dniu 22 czerwca 2026 r.",
            "Ogłoszenie o zamówieniu opublikowano w dniu 1 czerwca 2026 r.\n"
            "Termin składania ofert upływa 30 czerwca 2026 r.",
        )
        self.assertEqual(output["OdwolanieKIO"]["data"], "2026-06-18")
        self.assertEqual(output["OdwolanieKIO"]["czynnosc_dzien"], "2026-06-10")
        self.assertEqual(proof["OdwolanieKIO.czynnosc_dzien"]["page"], 2)

    def test_notice_has_to_refer_to_the_first_contested_act(self):
        output, proof = self.get_appeal(
            "Wnoszę odwołanie od następujących czynności:",
            "1. czynności unieważnienia postępowania, o której zamawiający zawiadomił "
            "wykonawców 8 czerwca 2026 roku;\n"
            "2. odmowy udostępnienia akt z dnia 13 czerwca 2026 r.\n"
            "Stopka, 25 czerwca 2026 r.",
        )
        self.assertEqual(output["OdwolanieKIO"]["czynnosc_dzien"], "2026-06-08")
        self.assertEqual(proof["OdwolanieKIO.czynnosc_dzien"]["page"], 3)

    def test_dates_for_publication_deadline_and_footer_are_not_act_dates(self):
        output, proof = self.get_appeal(
            "Wnoszę odwołanie od czynności wykluczenia wykonawcy, "
            "w postępowaniu z ogłoszeniem opublikowanym w dniu 1 czerwca 2026 r.\n"
            "Termin składania ofert upływa w dniu 30 czerwca 2026 r.\n"
            "Stopka: wydrukowano 25 czerwca 2026 r.\n"
            "Wnoszę o unieważnienie decyzji do dnia 28 czerwca 2026 r."
        )
        self.assertIsNone(output["OdwolanieKIO"]["czynnosc_dzien"])
        self.assertNotIn("OdwolanieKIO.czynnosc_dzien", proof)

    def test_publication_date_can_be_the_act_when_its_publication_is_challenged(self):
        output, proof = self.get_appeal(
            "Wnoszę odwołanie od opublikowania specyfikacji warunków zamówienia w dniu 4 czerwca 2026 r.\n"
            "Inne ogłoszenie opublikowano 2 czerwca 2026 r."
        )
        self.assertEqual(output["OdwolanieKIO"]["czynnosc_dzien"], "2026-06-04")
        self.assertEqual(proof["OdwolanieKIO.czynnosc_dzien"]["page"], 2)

    def test_procedure_fields_and_their_pages_are_independent(self):
        pages = (
            "Postępowanie nr INF/8.24/R\n"
            "Ogłoszenie o zamówieniu: 2026/BZP 00123456/02\n"
            "Postępowanie o udzielenie zamówienia publicznego pod nazwą „Remont skrzydła szkolnego”.",
            "Wnoszę odwołanie wobec odrzucenia oferty.\n"
            "Sygnatura akt: KIO/432/26\nNumer faktury: FV/36/06",
        )
        output, proof = self.get_appeal(*pages)
        procedure = output["ZamowieniePubliczne"]
        self.assertEqual(procedure["numer_postepowania"], "INF/8.24/R")
        self.assertEqual(procedure["numer_bzp"], "2026/BZP00123456/02")
        self.assertIsNone(procedure["numer_ted"])
        self.assertEqual(procedure["tytul"], "Remont skrzydła szkolnego")
        for field in ("numer_postepowania", "numer_bzp", "tytul"):
            self.assertEqual(proof[f"ZamowieniePubliczne.{field}"]["page"], 2)
        self.assertEqual(output["Zamawiajacy"][0]["nazwa"], "Fikcyjna gmina")

    def test_foreign_quoted_action_date_does_not_enter_the_result(self):
        output, proof = self.get_appeal(
            "Treść przytoczonego odwołania innego wykonawcy:\n"
            "Wnoszę odwołanie od wykluczenia wykonawcy z dnia 2 czerwca 2026 r.\n"
            "Koniec przytoczenia.\n"
            "Wnoszę odwołanie wobec decyzji o odrzuceniu oferty z dnia 9 czerwca 2026 r."
        )
        self.assertEqual(output["OdwolanieKIO"]["czynnosc_dzien"], "2026-06-09")
        self.assertEqual(proof["OdwolanieKIO.czynnosc_dzien"]["page"], 2)


    def test_date_on_a_wrapped_ocr_line_has_a_physical_page(self):
        output, proof = self.get_appeal(
            "Wnoszę odwołanie wobec:",
            "1. treści wyjaśnień SWZ udostępnionych przez Zamawiającego\n"
            "kwietnia 2026 r.;\n\n na stronie w dniu 7\n\n"
            "2. zaniechania uzasadnienia wyboru w dniu 16 czerwca 2026 roku.",
        )
        self.assertEqual(output["OdwolanieKIO"]["czynnosc_dzien"], "2026-04-07")
        self.assertEqual(proof["OdwolanieKIO.czynnosc_dzien"]["page"], 3)

    def test_subtitle_can_open_the_list_without_a_filing_formula(self):
        output, proof = self.get_appeal(
            "od czynności i zaniechań Zamawiającego\n\nwobec: .\n"
            "1. modyfikacji SWZ opublikowanej w dniu 9 czerwca 2026 r.;\n"
            "2. braku publikacji dokumentacji w dniu 8 czerwca 2026 r.",
        )
        self.assertEqual(output["OdwolanieKIO"]["czynnosc_dzien"], "2026-06-09")
        self.assertEqual(proof["OdwolanieKIO.czynnosc_dzien"]["page"], 2)

    def test_ted_publication_number_and_title_after_ocr_damage(self):
        output, proof = self.get_appeal(
            "Dotyczy: zamówienia pn. Modernizacja szkolnej kotłowni”, nr referencyjny: SM/18/26,\n"
            "ogłoszenie w Dzienniku Urzędowym Unii\nEuropejskiej nr 2026/5 61-123876\n"
            "Wnoszę odwołanie od wyboru oferty.",
        )
        procedure = output["ZamowieniePubliczne"]
        self.assertEqual(procedure["tytul"], "Modernizacja szkolnej kotłowni")
        self.assertEqual(procedure["numer_ted"], "123876-2026")
        self.assertEqual(procedure["numer_postepowania"], "SM/18/26")
        self.assertEqual(proof["ZamowieniePubliczne.numer_ted"]["page"], 2)

    def test_ted_issue_like_reference_outside_ue_journal_is_ignored(self):
        output, _ = self.get_appeal(
            "Oznaczenie zamówienia: 2026/5 61-123876\n"
            "Wnoszę odwołanie od wyboru oferty.",
        )
        self.assertIsNone(output["ZamowieniePubliczne"]["numer_ted"])

    def test_ocr_dots_in_a_company_name_do_not_hide_the_notice(self):
        output, proof = self.get_appeal(
            "Wnoszę odwołanie wobec: ",
            "1. zaniechania odrzucenia oferty wykonawcy Projekt . Fikcyjny S.A., "
            "która podlegała odrzuceniu, o czym odwołujący otrzymał wiadomość w dniu 11.06.2026 r.;"
        )
        self.assertEqual(output["OdwolanieKIO"]["czynnosc_dzien"], "2026-06-11")
        self.assertEqual(proof["OdwolanieKIO.czynnosc_dzien"]["page"], 3)
