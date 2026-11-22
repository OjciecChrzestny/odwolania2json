"""Role pełnomocnictwa odtwarzane z fikcyjnych dokumentów."""
from dataclasses import replace
import unittest

from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes
from test_podpisy import footer_tsv


def parse(*pages):
    return extract(Document.from_pages(pages), load_classes())


HEADER = """PEŁNOMOCNICTWO
Przykładowe Zakłady
Północy S.A.
z siedzibą w Fikcyjnym Mieście, KRS: 0001234567,
niniejszym udziela pełnomocnictwa:
"""
APPOINTMENTS = """1. Emilia Żuraw — radca prawny, nr wpisu R-12, PESEL: 01234567890,
2. Marek Ptak — adwokat, nr wpisu A-77,
do reprezentowania przed Izbą.
"""


class PartyRolesTest(unittest.TestCase):
    def test_numbered_names_source_spans_and_integer_pesel(self):
        data, evidence = parse(HEADER + APPOINTMENTS)
        self.assertEqual(data["pelnomocnicy"], [
            {"imie_nazwisko": "Emilia Żuraw", "pesel": 1234567890},
            {"imie_nazwisko": "Marek Ptak", "pesel": None},
        ])
        fields = evidence["fields"]
        self.assertEqual(fields["pelnomocnicy.0.imie_nazwisko"]["snippet"], "Emilia Żuraw")
        self.assertEqual(fields["pelnomocnicy.0.imie_nazwisko"]["page"], 1)
        self.assertEqual(fields["pelnomocnicy.0.pesel"]["snippet"], "01234567890")

    def test_company_name_stops_before_registered_office_on_next_line(self):
        data, _ = parse(HEADER + APPOINTMENTS)
        self.assertEqual(data["mocodawca"][0]["data"]["nazwa"], "Przykładowe Zakłady Północy S.A.")
        self.assertEqual(data["mocodawca"][0]["data"]["krs"], "0001234567")

    def test_one_person_declaration_has_separate_name_and_address(self):
        data, evidence = parse("""PEŁNOMOCNICTWO
Ja, niżej podpisany/a Adam Fikcyjny, prowadzący/a działalność gospodarczą
w Fikcyjnym Mieście, ul. Przykładowa 18, NIP: 0123456789,
niniejszym udzielam pełnomocnictwa:
""" + APPOINTMENTS)
        principal = data["mocodawca"][0]["data"]
        self.assertEqual(principal, {"imie_nazwisko": "Adam Fikcyjny", "nazwa": None, "nip": "0123456789",
                                     "krs": None, "typ": "osoba_fizyczna"})
        proof = evidence["fields"]["mocodawca.0.data.imie_nazwisko"]
        self.assertEqual((proof["page"], proof["snippet"]), (1, "Adam Fikcyjny"))

    def test_receipt_and_instructions_are_not_numbered_counsel(self):
        for heading in ("Potwierdzenie odbioru:", "Pouczenie:", "Cytat:", "Świadek:"):
            with self.subTest(heading=heading):
                data, _ = parse(HEADER + heading + "\n" + APPOINTMENTS)
                self.assertEqual(data["pelnomocnicy"], [])

    def test_numbering_gap_abstains_instead_of_shifting_indices(self):
        data, _ = parse(HEADER + APPOINTMENTS.replace("2. Marek", "3. Marek"))
        self.assertEqual(data["pelnomocnicy"], [])

    def test_cover_page_does_not_become_an_appointment(self):
        text = HEADER.replace("PEŁNOMOCNICTWO", "PEŁNOMOCNICTWO DO REPREZENTACJI") + APPOINTMENTS
        data, evidence = parse("Pismo przewodnie\nW załączeniu.", text)
        self.assertEqual(data["pelnomocnicy"][1]["imie_nazwisko"], "Marek Ptak")
        self.assertEqual(evidence["fields"]["pelnomocnicy.1.imie_nazwisko"]["page"], 2)

    def test_electronic_certificate_needs_matching_principal_and_timestamp(self):
        intro = HEADER.replace("niniejszym udziela", "reprezentowana przez: Ewa Próbna — Prezes Zarządu,\n"
                               "niniejszym udziela") + APPOINTMENTS
        cert = "Dokument podpisany przez Ewa Próbna\nData: 2032.03.15 11:08:04\n"
        doc = Document.from_pages([intro + cert])
        data, evidence = extract(replace(doc, ocr_layout_tsv=footer_tsv(cert)), load_classes())
        self.assertEqual(data["mocodawca"][0]["podpisujacy"], [{"imie_nazwisko": "Ewa Próbna"}])
        proof = evidence["fields"]["mocodawca.0.podpisujacy.0.imie_nazwisko"]
        self.assertEqual((proof["page"], proof["source"], proof["snippet"]), (1, "ocr", "Ewa Próbna"))

        for alternate in (cert.replace("Ewa Próbna", "Daniel Testowy"), cert.replace(" 11:08:04", ""),
                          "Poświadczenie kopii:\n" + cert, "Odbiór dokumentu:\n" + cert,
                          "Nie podpisano.\n" + cert):
            doc = Document.from_pages([intro + alternate])
            data, _ = extract(replace(doc, ocr_layout_tsv=footer_tsv(alternate)), load_classes())
            self.assertEqual(data["mocodawca"][0]["podpisujacy"], [])


if __name__ == "__main__":
    unittest.main()
