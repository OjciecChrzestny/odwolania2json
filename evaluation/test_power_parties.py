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

        missed_letter = cert.replace("podpisany", "podpiany")
        document = Document.from_pages([intro + missed_letter])
        value, _ = extract(replace(document, ocr_layout_tsv=footer_tsv(missed_letter)), load_classes())
        self.assertEqual(value["mocodawca"][0]["podpisujacy"], [{"imie_nazwisko": "Ewa Próbna"}])

        for alternate in (cert.replace("Ewa Próbna", "Daniel Testowy"), cert.replace(" 11:08:04", ""),
                          "Poświadczenie kopii:\n" + cert, "Odbiór dokumentu:\n" + cert,
                          "Nie podpisano.\n" + cert):
            doc = Document.from_pages([intro + alternate])
            data, _ = extract(replace(doc, ocr_layout_tsv=footer_tsv(alternate)), load_classes())
            self.assertEqual(data["mocodawca"][0]["podpisujacy"], [])


    def test_legal_form_corrects_zeros_only_in_ocr_company_suffix(self):
        text = HEADER.replace("Północy S.A.", "Północy Sp. z 0.0.") + APPOINTMENTS
        doc = Document.from_pages([text])
        native, _ = extract(doc, load_classes())
        self.assertEqual(native["mocodawca"][0]["data"]["nazwa"], "Przykładowe Zakłady Północy Sp. z 0.0.")
        wide, proof = extract(replace(doc, ocr_layout_tsv="wiersze"), load_classes())
        self.assertEqual(wide["mocodawca"][0]["data"]["nazwa"], "Przykładowe Zakłady Północy Sp. z o.o.")
        self.assertEqual(proof["fields"]["mocodawca.0.data.nazwa"]["source"], "ocr")

    def test_follows_physical_indent_before_skipping_ocr_margin_glyph(self):
        row = "J 1. Emilia Żuraw — radca prawny, nr wpisu W-15,"
        text = HEADER + row + "\ndo reprezentowania przed Izbą."
        doc = Document.from_pages([text])
        near, _ = extract(replace(doc, ocr_layout_tsv=footer_tsv(row)), load_classes())
        self.assertEqual(near["pelnomocnicy"], [])
        layout = []
        for raw in footer_tsv(row).splitlines():
            columns = raw.split("\t")
            if columns[5] == "1":
                columns[10] = "18"
            else:
                columns[6] = str(100 + int(columns[6]))
            layout.append("\t".join(columns))
        data, evidence = extract(replace(doc, ocr_layout_tsv="\n".join(layout)), load_classes())
        self.assertEqual(data["pelnomocnicy"], [{"imie_nazwisko": "Emilia Żuraw", "pesel": None}])
        self.assertEqual(evidence["fields"]["pelnomocnicy.0.imie_nazwisko"]["snippet"], "Emilia Żuraw")


    def test_only_aligned_continuation_of_existing_roster_can_restore_initial_case(self):
        lines = "Eva Próbna\nAdam Letni\nkamil Kozioł"
        doc = Document.from_pages([HEADER + lines + "\ndo reprezentowania przed Izbą."])
        before, _ = extract(doc, load_classes())
        self.assertEqual(len(before["pelnomocnicy"]), 2)
        data, evidence = extract(replace(doc, ocr_layout_tsv=footer_tsv(lines)), load_classes())
        expected = before["pelnomocnicy"] + [{"imie_nazwisko": "Kamil Kozioł", "pesel": None}]
        self.assertEqual(data["pelnomocnicy"], expected)
        self.assertEqual(evidence["fields"]["pelnomocnicy.2.imie_nazwisko"]["precision"], "page")
        broken_layout = footer_tsv(lines).replace("\t3\t1\t30\t90", "\t3\t1\t90\t90")
        data, _ = extract(replace(doc, ocr_layout_tsv=broken_layout), load_classes())
        self.assertEqual(data["pelnomocnicy"], before["pelnomocnicy"])


if __name__ == "__main__":
    unittest.main()
