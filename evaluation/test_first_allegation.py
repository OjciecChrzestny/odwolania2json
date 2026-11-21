"""Regresje wyboru pierwszego zarzutu. Wszystkie strony są fikcyjne."""
import unittest

from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


COVER = ("Krajowa Izba Odwoławcza\nOdwołujący: Fikcyjna spółka\n"
         "Zamawiający: Fikcyjna gmina\nODWOŁANIE")
CASES = {
    # Strony po okładce, ID, data, strona dowodu, fragment rozstrzygający.
    "podstawa_i_zadania": (
        (
            "Na podstawie art. 513 Pzp wnoszę odwołanie.\n"
            "Zamawiający w dniu 2 stycznia 2026 r. dokonał wyboru oferty.\n"
            "Żądania\nWnoszę o unieważnienie postępowania.",
            "Zarzuty odwołania\n1. Naruszenie art. 226 ustawy Pzp (przesłanki odrzucenia oferty),",
            "poprzez zaniechanie wykluczenia wykonawcy.\n2. Naruszenie art. 239 Pzp "
            "przez wybór oferty.",
        ), 8, None, 4, "zaniechanie wykluczenia wykonawcy",
    ),
    "dluga_podstawa": (
        (
            "Zarzut pierwszy: Naruszenie art. 226 ust. 1 Pzp (przesłanki odrzucenia oferty) "
            "w związku z art. 16 ust. 1 Pzp oraz art. 17 ust. 2 Pzp, "
            "w związku z zasadą uczciwej konkurencji i równego traktowania wykonawców, "
            "a także z uwzględnieniem obowiązków wynikających z zasad prowadzenia postępowania, "
            "poprzez modyfikację treści SWZ w dniu 4 stycznia 2026 r.\n"
            "Zarzut II: Wybór oferty.",
        ), 5, "2026-01-04", 2, "modyfikację treści SWZ",
    ),
    "zarzut_bez_numeru": (
        (
            "Podstawą wniesienia pisma jest art. 513 Pzp.\n"
            "Zamawiający w dniu 2 stycznia 2026 r. dokonał wyboru oferty.",
            "Odwołujący zarzuca Zamawiającemu zaniechanie odrzucenia oferty.\n"
            "Odwołujący zarzuca Zamawiającemu wykluczenie wykonawcy.",
        ), 7, None, 3, "zaniechanie odrzucenia oferty",
    ),
    "sama_podstawa": (
        (
            "Zarzut 1: Naruszenie art. 226 Pzp (przesłanki odrzucenia oferty).\n"
            "Wnioski końcowe\nZaniechanie wykluczenia wykonawcy powinno zostać stwierdzone.",
        ), 11, None, 2, None,
    ),
    "obcy_wstep_przed_lista": (
        (
            "Informacja o czynnościach polegających na:\n"
            "Komunikat przekazano uczestnikom.\n"
            "Zarzuty:\n1) Unieważnienie postępowania.\n2) Wybór oferty.",
        ), 9, None, 2, "Unieważnienie postępowania",
    ),
    "zadania_po_zarzucie": (
        (
            "Zarzut 1: Uchybienie obowiązkowi przejrzystości.\n"
            "Żądania odwołania\nUnieważnienie postępowania.",
        ), 11, None, 2, None,
    ),
    "data_przepisu": (
        (
            "Zarzut I: Naruszenie art. 226 ustawy z dnia 11 września 2019 r. "
            "przez odrzucenie oferty.\nZarzut II: Wybór oferty.",
        ), 1, None, 2, "odrzucenie oferty",
    ),
    "lista_przez_granice_stron": (
        (
            "Wnoszę odwołanie wobec niezgodnych z ustawą czynności\nStrona 2 z 4",
            "i zaniechań Zamawiającego, polegających na:\n"
            "1) modyfikacji treści SWZ z dnia 12 czerwca 2026 r.;\n"
            "2) zaniechaniu wykluczenia wykonawcy.",
            "Zarzut 1: Modyfikacja treści SWZ.",
        ), 5, "2026-06-12", 3, "modyfikacji treści SWZ",
    ),
    "lista_zadan_przed_zarzutem": (
        (
            "Wnoszę odwołanie wobec dokumentacji.\n"
            "Żądania\nUsunięcia skutków polegających na:\n"
            "1) unieważnieniu postępowania;\n2) wyborze oferty.",
            "Zarzut pierwszy: Odrzucenie oferty.",
        ), 1, None, 3, "Odrzucenie oferty",
    ),
}


class AllegationSelectionTest(unittest.TestCase):
    def test_reason_date_and_source(self):
        config = load_classes()
        descriptions = config["odwolanie"]["reasons"]["descriptions"]
        for name, (pages, reason, date, page, phrase) in CASES.items():
            with self.subTest(name=name):
                document = Document.from_pages([COVER, *pages])
                value, details = extract(document, config, capture_decision=True)
                action = value["OdwolanieKIO"]
                self.assertEqual(action["czynnosc_powod_id"], reason)
                self.assertEqual(action["czynnosc_opis"], descriptions[str(reason)])
                self.assertEqual(action["czynnosc_dzien"], date)
                self.assertEqual(details["first_allegation"]["page"], page)
                self.assertEqual(details["first_allegation"]["fallback"], phrase is None)
                if phrase:
                    fragment = details["decision_fragment"]
                    position = fragment.offset + fragment.text.index(phrase)
                    self.assertEqual(document.text[position:position + len(phrase)], phrase)
                    self.assertEqual(document.page(position), page)
                    self.assertEqual(details["decision_source"]["page"], page)
                    self.assertNotIn("Wybór oferty.", fragment.text)
