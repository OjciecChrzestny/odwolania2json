"""Regresje ekstrakcji ról z fikcyjnych pełnomocnictw."""
import unittest

from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes


def principal(name, *signers, nip=None, krs=None):
    return {
        "data": {"imie_nazwisko": None, "krs": krs, "nazwa": name,
                 "nip": nip, "typ": "osoba_prawna"},
        "podpisujacy": [{"imie_nazwisko": signer} for signer in signers],
    }


def attorney(name, pesel=None):
    return {"imie_nazwisko": name, "pesel": pesel}


COMPANY = "Fikcyjna Północ sp. z o.o."
SECOND = "Testowe Południe S.A."
TITLE = "PEŁNOMOCNICTWO"
NOTICE = """Instrukcja wypełnienia formularza
PEŁNOMOCNICTWO
Fikcyjna Północ sp. z o.o. udziela pełnomocnictwa: adwokat Nina Zorza.
Podpis mocodawcy: radca prawny Roman Bór
"""
SIGNER_ONLY = f"""{TITLE}
{COMPANY}, ul. Fikcyjna 7, udziela pełnomocnictwa:
Podpis mocodawcy:
radca prawny Roman Bór
"""
CASES = {
    "01": (
        [f"""{TITLE}
Mocodawca: {COMPANY}, KRS 0000001234, NIP 0000005678
Reprezentowana przez: radcę prawnego Romana Bora
udziela pełnomocnictwa:
1. Nina Zorza (PESEL 12345678901)
2. Adam Ostoja (PESEL 10987654321)
do reprezentowania spółki przed Krajową Izbą Odwoławczą.
Podpis mocodawcy: Roman Bór — Prezes Zarządu
Pełnomocnictwo przyjmuję: Nina Zorza
"""],
        [principal(COMPANY, "Roman Bór", nip="0000005678", krs="0000001234")],
        [attorney("Nina Zorza", 12345678901), attorney("Adam Ostoja", 10987654321)],
    ),
    "02": (
        [f"""{TITLE}
{COMPANY}, z siedzibą w Mieście Testowym, udziela pełnomocnictwa.
Pełnomocnicy: Łucja Dąb, Iga Wiśnia i Jan Nowik
Zakres: reprezentacja w postępowaniu.
W imieniu {COMPANY}:
Ewa Żuraw
Tomasz Leśny — Członek Zarządu
Pełnomocnictwo przyjmuję:
adwokat Julia Wrzos
"""],
        [principal(COMPANY, "Ewa Żuraw", "Tomasz Leśny")],
        [attorney("Łucja Dąb"), attorney("Iga Wiśnia"), attorney("Jan Nowik")],
    ),
    "03": (
        [f"""{TITLE}
{COMPANY}, ul. Fikcyjna 7, udziela pełnomocnictwa:
adw. Ada Rosa, nr wpisu R-51
Zakres: reprezentacja przed Izbą.
Podpis mocodawcy:
radca prawny Jan Kłos
Pełnomocnictwo przyjmuję:
adwokat Łukasz Liść
"""],
        [principal(COMPANY, "Jan Kłos")],
        [attorney("Ada Rosa")],
    ),
    "04": (
        [f"""{TITLE}
{COMPANY}, ul. Fikcyjna 7, udziela pełnomocnictwa do reprezentowania spółki.
Pełnomocnictwo przyjmuję:
adw. Filip Wiatr
"""],
        [principal(COMPANY)], [],
    ),
    "05": (
        [f"""{TITLE}
Działając w imieniu podmiotów w składzie:
1. {SECOND}, NIP 2222222222;
2. {COMPANY}, NIP 1111111111
udzielamy pełnomocnictwa: radca prawny Ada Rosa, nr wpisu R-51
Zakres: reprezentacja przed Izbą.
""", f"""W imieniu {COMPANY}:
Podpisano elektronicznie przez: Milena Kora
W imieniu Inny podmiot S.A.:
Podpisano elektronicznie przez: Grzegorz Irys
W imieniu {SECOND}:
Podpisano elektronicznie przez: Zofia Gaj
"""],
        [principal(SECOND, "Zofia Gaj", nip="2222222222"),
         principal(COMPANY, "Milena Kora", nip="1111111111")],
        [attorney("Ada Rosa")],
    ),
    "06": (
        [f"""{TITLE}
{COMPANY}, ul. Fikcyjna 7, udziela pełnomocnictwa: adw. Nina Zorza;
adw. Olga Gaj (PESEL 10101010101).
Zakres: reprezentacja przed Izbą.
W imieniu Inna spółka S.A.:
.............................
Jacek Sroka
"""],
        [principal(COMPANY)],
        [attorney("Nina Zorza"), attorney("Olga Gaj", 10101010101)],
    ),
    "07": (
        [f"""{TITLE}
{COMPANY}, ul. Fikcyjna 7, udziela pełnomocnictwa:
Zakres obejmuje składanie pism przed Izbą.
Podpis mocodawcy:
radca prawny Roman Bór
Pełnomocnictwo przyjmuję:
adw. Filip Wiatr
"""],
        [principal(COMPANY, "Roman Bór")], [],
    ),
    "08": (
        [f"""{TITLE}
{COMPANY}, ul. Fikcyjna 7, udziela pełnomocnictwa: adw. Gaja Sosna
""", """do reprezentowania spółki przed Izbą.
Pełnomocnicy zamawiającego
adw. Adam Ptak
"""],
        [principal(COMPANY)], [attorney("Gaja Sosna")],
    ),
}


class PowerOfAttorneyRolesTest(unittest.TestCase):
    def test_named_roles_and_list_order(self):
        classes = load_classes()
        for number, (pages, principals, attorneys) in CASES.items():
            with self.subTest(case=number):
                result, diagnostics = extract(Document.from_pages(pages), classes)
                self.assertEqual(diagnostics["class"], "pelnomocnictwo")
                self.assertEqual(result, {"mocodawca": principals, "pelnomocnicy": attorneys})
                if number == "05":
                    self.assertEqual(diagnostics["fields"]["mocodawca.0.podpisujacy.0.imie_nazwisko"]["page"], 2)
                    self.assertEqual(diagnostics["fields"]["pelnomocnicy.0.imie_nazwisko"]["page"], 1)

    def test_instruction_with_copied_grant_and_signature_stays_negative(self):
        result, diagnostics = extract(Document.from_pages([NOTICE]), load_classes())
        self.assertIsNone(result)
        self.assertEqual(diagnostics["class"], "negative")


    def test_personal_data_of_representative_does_not_change_the_principal_type(self):
        text = f"""{TITLE}
{COMPANY}, reprezentowana przez Ewę Żuraw, PESEL 11111111111,
udziela pełnomocnictwa:
r. pr. Ada Rosa (nr wpisu: R-51)
r. pr. Nina Zorza
nr wpisu R 62
Biuro Obsługi
Podpis mocodawcy:
Prezes Zarządu
Ewa Żuraw
"""
        result, _ = extract(Document.from_pages([text]), load_classes())
        self.assertEqual(result, {"mocodawca": [principal(COMPANY, "Ewa Żuraw")],
                                  "pelnomocnicy": [attorney("Ada Rosa"), attorney("Nina Zorza")]})


    def test_signature_with_a_legal_title_is_not_an_appointment(self):
        result, diagnostics = extract(Document.from_pages([SIGNER_ONLY]), load_classes())
        self.assertEqual(result, {"mocodawca": [principal(COMPANY, "Roman Bór")], "pelnomocnicy": []})
        self.assertEqual(diagnostics["fields"]["mocodawca.0.podpisujacy.0.imie_nazwisko"]["page"], 1)


    def test_company_suffix_spacing_keeps_signature_with_its_principal(self):
        pages, principals, attorneys = CASES["05"]
        changed = [pages[0].replace("sp. z o.o.", "sp. zo.o."), pages[1]]
        result, _ = extract(Document.from_pages(changed), load_classes())
        self.assertEqual(result, {"mocodawca": principals, "pelnomocnicy": attorneys})
