"""Dwa źródła podpisu, przypisanie mocodawcy i zachowanie dowodu."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from pypdf import PdfWriter

from odwolania2json.extract import extract, read_pdf
from odwolania2json.legal import Fragment, principal_blocks
from odwolania2json.model import Document, Extraction, load_classes
from odwolania2json.ocr import LocalOCR
from odwolania2json.podpisy import SIGNATURE_RULE, _signature_guide, add_confirmed_signatures

HEADER = """PEŁNOMOCNICTWO
Przykładowy Podmiot sp. z o.o., ul. Przykładowa 1, udziela pełnomocnictwa:
radca prawny Nina Zorza
do reprezentowania przed Krajową Izbą Odwoławczą.
Zakres: czynności w postępowaniu.
"""

NEGATIVES = {
    "witness_with_office": (
        HEADER + "Świadek złożenia podpisu\nJan Nowik — Prezes Zarządu\n",
        "pelnomocnictwo", ["Nina Zorza"], [[]],
    ),
    "officer_only_in_preamble": (
        """PEŁNOMOCNICTWO
Przykładowy Podmiot sp. z o.o., z siedzibą w Fikcyjnym Mieście,
reprezentowany przez: Emilia Ptak — Prezes Zarządu
udziela pełnomocnictwa: adw. Nina Zorza
do reprezentowania przed Krajową Izbą Odwoławczą.
""",
        "pelnomocnictwo", ["Nina Zorza"], [[]],
    ),
    "attorney_acceptance": (
        HEADER + """Pełnomocnictwo przyjmuję:
radca prawny Nina Zorza
(podpis pełnomocnika)
""",
        "pelnomocnictwo", ["Nina Zorza"], [[]],
    ),
    "technical_signature": (
        HEADER + """Sprawdzenie integralności pliku:
Podpisano elektronicznie przez: Tadeusz Sowa
Administrator systemu
""",
        "pelnomocnictwo", ["Nina Zorza"], [[]],
    ),
    "two_owners_no_links": (
        """PEŁNOMOCNICTWO
Działając w imieniu podmiotów w składzie:
1. Fikcyjna Północ sp. z o.o., NIP 1111111111;
2. Przykładowe Południe S.A., NIP 2222222222
udzielamy pełnomocnictwa: adwokat Nina Zorza
do reprezentowania podmiotów.
Zakres: czynności w postępowaniu.
Podpisy mocodawców
Joanna Kłos — Prezes Zarządu
Łucja Żuraw — Członek Zarządu
""",
        "pelnomocnictwo", ["Nina Zorza"], [[], []],
    ),
    "clerk_outside_mandate": (
        HEADER + """Kopia do wiadomości:
radca prawny Adam Ptak
Podpis osoby przekazującej kopię: Joanna Kłos
""",
        "pelnomocnictwo", ["Nina Zorza"], [[]],
    ),
    "quoted_example": (
        "Instrukcja wypełnienia formularza\n" + HEADER + "Podpis mocodawcy: Roman Bór\n",
        "negative", [], [],
    ),
}

PREAMBLE = """PEŁNOMOCNICTWO
Przykładowa Północ sp. z o.o., ul. Przykładowa 1,
reprezentowana przez: Roman Bór — Prezes Zarządu, Emilia Ptak — Członek Zarządu,
niniejszym udziela pełnomocnictwa:
radca prawny Nina Zorza
do reprezentowania przed Izbą.
Zakres: czynności w postępowaniu.
"""
CONSORTIUM = """PEŁNOMOCNICTWO
Działając w imieniu podmiotów w składzie:
1. Przykładowa Północ sp. z o.o., NIP 1111111111, reprezentowana przez: Roman Bór — Prezes Zarządu;
2. Fikcyjne Południe S.A., NIP 2222222222, reprezentowana przez: Emilia Ptak — Członek Zarządu
niniejszym udzielamy pełnomocnictwa:
radca prawny Nina Zorza
do reprezentowania przed Izbą.
Zakres: czynności w postępowaniu.
"""


def footer_tsv(block):
    return "\n".join("\t".join(map(str, (5, 1, 1, 1, line, index, index * 30, line * 30, 25, 20, 95, token)))
                     for line, text in enumerate(block.splitlines(), 1)
                     for index, token in enumerate(text.split(), 1))


def apply_signatures(doc, obj, config, tsv):
    result = Extraction(doc, config["schema"])
    result.data = deepcopy(obj)
    fragment = Fragment(doc.text)
    add_confirmed_signatures(result, config, fragment, principal_blocks(fragment, config), tsv)
    updates = {index: [signer["imie_nazwisko"] for signer in row["podpisujacy"]]
               for index, row in enumerate(result.data["mocodawca"])
               if row["podpisujacy"] != obj["mocodawca"][index]["podpisujacy"]}
    return updates, result.evidence


class RoleRecoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def check(self, body, footer_layout):
        doc = Document.from_pages([body])
        obj, meta = extract(doc, self.classes)
        if meta["class"] != "pelnomocnictwo":
            return obj, meta, {}
        config = self.classes["pelnomocnictwo"]
        updates, _ = apply_signatures(doc, obj, config, footer_tsv(footer_layout))
        return obj, meta, updates

    def test_preserves_preamble_order_when_ocr_footer_order_is_inverted(self):
        scan_order = "Emilia Ptak — Członek Zarządu Roman Bór — Prezes Zarządu\nZa Mocodawcę:"
        visual_order = "Za Mocodawcę:\nEmilia Ptak — Członek Zarządu Roman Bór — Prezes Zarządu"
        obj, _, updates = self.check(PREAMBLE + scan_order, visual_order)
        self.assertEqual(updates, {0: ["Roman Bór", "Emilia Ptak"]})
        self.assertEqual(obj["pelnomocnicy"], [{"imie_nazwisko": "Nina Zorza", "pesel": None}])

    def test_representation_binds_signature_to_one_of_two_principals(self):
        footer = "Za Mocodawcę:\nEmilia Ptak — Członek Zarządu\nRoman Bór — Prezes Zarządu"
        _, _, updates = self.check(CONSORTIUM + footer, footer)
        self.assertEqual(updates, {0: ["Roman Bór"], 1: ["Emilia Ptak"]})

    def test_blank_signature_slots_with_or_without_recognized_rules(self):
        header = "Za Mocodawcę:"
        first = "Roman Bór — Prezes Zarządu"
        second = "Emilia Ptak — Członek Zarządu"
        body = PREAMBLE + "\n".join((header, first, second))
        doc = Document.from_pages([body])
        obj, _ = extract(doc, self.classes)
        config = self.classes["pelnomocnictwo"]

        for physical in (
            (header, "", "", first, "", "", second),
            (header, "________", first, "________", second),
            (header, "_ | —", "", first, "", "", second),
        ):
            with self.subTest(physical=physical):
                updates, evidence = apply_signatures(doc, obj, config, footer_tsv("\n".join(physical)))
                self.assertEqual(updates, {})
                self.assertEqual(evidence, {})

        fully_marked = "\n".join((header, "_ | —", "", first, "= / _", "", second))
        updates, evidence = apply_signatures(doc, obj, config, footer_tsv(fully_marked))
        self.assertEqual(updates, {0: ["Roman Bór", "Emilia Ptak"]})
        self.assertTrue(all(field["page"] == 1 for field in evidence.values()))

    def test_individual_form_evidence_uses_footer_positions_and_declaration_order(self):
        footer = "Za Mocodawcę:\n\n\nEmilia Ptak — Członek Zarządu\n\n\nRoman Bór — Prezes Zarządu"
        doc = Document.from_pages([PREAMBLE + footer])
        obj, _ = extract(doc, self.classes)
        config = self.classes["pelnomocnictwo"]
        for observations, names in (
            ([(True, False), (True, True)], ["Roman Bór"]),
            ([(True, True), (True, True)], ["Roman Bór", "Emilia Ptak"]),
            ([(True, False), (True, False)], []),
        ):
            with self.subTest(observations=observations):
                def scan(boxes):
                    self.assertLess(boxes[0][1], boxes[1][1])
                    return observations

                scan_doc = replace(doc, signature_guides=scan)
                updates, evidence = apply_signatures(scan_doc, obj, config, footer_tsv(footer))
                self.assertEqual(updates, {0: names} if names else {})
                self.assertEqual(len(evidence), len(names))
                self.assertTrue(all(field["page"] == 1 for field in evidence.values()))

    def test_a_horizontal_rule_is_not_ink_above_a_signature_guide(self):
        bitmap = SimpleNamespace(width=110, height=100, stride=110)
        pixels = bytearray([255]) * (bitmap.width * bitmap.height)
        for x in range(10, 100):
            pixels[80 * bitmap.stride + x] = 0
        box = (5, 10, 105, 89, 20)
        self.assertEqual(_signature_guide(bitmap, pixels, box), (True, False))
        for row in range(43, 69):
            x = row - 24
            pixels[row * bitmap.stride + x:row * bitmap.stride + x + 3] = bytes(3)
        self.assertEqual(_signature_guide(bitmap, pixels, box), (True, True))

    def test_frozen_independent_negatives(self):
        for case, (body, kind, counsel, signatures) in NEGATIVES.items():
            with self.subTest(case=case):
                obj, meta, updates = self.check(body, body)
                self.assertEqual(meta["class"], kind)
                self.assertEqual(updates, {})
                if obj:
                    self.assertEqual([item["imie_nazwisko"] for item in obj["pelnomocnicy"]], counsel)
                    self.assertEqual([[person["imie_nazwisko"] for person in row["podpisujacy"]]
                                      for row in obj["mocodawca"]], signatures)

    def test_explicit_footer_cannot_promote_ambiguous_or_external_name(self):
        variants = {
            "missing_first": "Za Mocodawcę:\nEmilia Ptak — Członek Zarządu",
            "unmatched_name": "Za Mocodawcę:\nRoman Bar — Prezes Zarządu\nEmilia Ptak — Członek Zarządu",
            "witness_section": "Za Mocodawcę:\nŚwiadek:\nRoman Bór — Prezes Zarządu\nEmilia Ptak — Członek Zarządu",
            "copy_section": "Za Mocodawcę:\nKopia do wiadomości:\nRoman Bór — Prezes Zarządu\nEmilia Ptak — Członek Zarządu",
            "acceptance_followed_by_footer": "Pełnomocnictwo przyjmuję:\nZa Mocodawcę:\n"
                                              "Roman Bór — Prezes Zarządu\nEmilia Ptak — Członek Zarządu",
            "extra_official": "Za Mocodawcę:\nRoman Bór — Prezes Zarządu\nEmilia Ptak — Członek Zarządu\n"
                              "Joanna Kłos — Prokurent",
            "split_name_unrelated_lines": "Za Mocodawcę:\nRoman\nBór\nEmilia Ptak — Członek Zarządu",
        }
        for case, footer in variants.items():
            with self.subTest(case=case):
                _, _, updates = self.check(PREAMBLE + footer, footer)
                self.assertEqual(updates, {})

    def test_explicit_absence_vetoes_even_matching_signature_shaped_rows(self):
        people = "Roman Bór — Prezes Zarządu\nEmilia Ptak — Członek Zarządu"
        for message in ("Nie podpisano.", "Brak podpisów w chwili przekazania.",
                        "Nie złożono żadnego podpisu.", "Brak\npodpisu"):
            for block in (message + "\n" + people, people + "\n" + message):
                with self.subTest(message=message, block=block):
                    footer = "Za Mocodawcę:\n" + block
                    _, _, updates = self.check(PREAMBLE + footer, footer)
                    self.assertEqual(updates, {})

    def test_other_roles_or_free_prose_do_not_extend_the_local_signature_block(self):
        people = "Roman Bór — Prezes Zarządu\nEmilia Ptak — Członek Zarządu"
        for role in ("Osoby uprawnione do złożenia podpisu:", "Wykaz osób upoważnionych:",
                     "Odbiór dokumentu potwierdzili:", "Podpis odbiorcy:",
                     "Lista uczestników spotkania:", "W dalszej części podano skład zarządu."):
            with self.subTest(role=role):
                footer = f"Za Mocodawcę:\n{role}\n{people}"
                _, _, updates = self.check(PREAMBLE + footer, footer)
                self.assertEqual(updates, {})

        for people in ("Roman Bór oraz Emilia Ptak.", "Roman Bór\nEmilia Ptak",
                       "Roman Bór — Prezes Zarządu, który potwierdził odbiór\nEmilia Ptak — Członek Zarządu"):
            with self.subTest(people=people):
                footer = "Za Mocodawcę:\n" + people
                _, _, updates = self.check(PREAMBLE + footer, footer)
                self.assertEqual(updates, {})

    def test_graphic_fragments_and_one_unlabelled_row_can_belong_to_the_same_block(self):
        footer = "Za Mocodawcę:\n_ | —\nRoman Bór =\nEmilia Ptak — Członek Zarządu"
        _, _, updates = self.check(CONSORTIUM + footer, footer)
        self.assertEqual(updates, {0: ["Roman Bór"], 1: ["Emilia Ptak"]})

    def test_two_principals_with_same_representative_are_ambiguous(self):
        body = CONSORTIUM.replace("Emilia Ptak — Członek Zarządu", "Roman Bór — Prezes Zarządu")
        footer = "Za Mocodawcę:\nRoman Bór — Prezes Zarządu"
        _, _, updates = self.check(body + footer, footer)
        self.assertEqual(updates, {})

    def test_does_not_use_a_layout_from_one_page_for_a_multipage_document(self):
        footer = "Za Mocodawcę:\nRoman Bór — Prezes Zarządu\nEmilia Ptak — Członek Zarządu"
        doc = Document.from_pages([PREAMBLE, footer])
        obj, _ = extract(doc, self.classes)
        self.assertEqual(apply_signatures(doc, obj, self.classes["pelnomocnictwo"], footer_tsv(footer)), ({}, {}))

    def test_keeps_existing_nonempty_signature_lists_intact(self):
        footer = "Za Mocodawcę:\nRoman Bór — Prezes Zarządu\nEmilia Ptak — Członek Zarządu"
        doc = Document.from_pages([PREAMBLE + footer])
        obj, _ = extract(doc, self.classes)
        obj["mocodawca"][0]["podpisujacy"] = [{"imie_nazwisko": "Roman Bór"}]
        self.assertEqual(apply_signatures(doc, obj, self.classes["pelnomocnictwo"], footer_tsv(footer)), ({}, {}))

    def test_records_ocr_page_without_inventing_a_text_span(self):
        footer = "Za Mocodawcę:\nRoman Bór — Prezes Zarządu\nEmilia Ptak — Członek Zarządu"
        document = Document.from_pages([PREAMBLE + footer])
        value, _ = extract(document, self.classes)
        _, evidence = apply_signatures(document, value, self.classes["pelnomocnictwo"], footer_tsv(footer))
        expected = {"page": 1, "rule": SIGNATURE_RULE, "source": "ocr", "precision": "page"}
        for index in (0, 1):
            self.assertEqual(evidence[f"mocodawca.0.podpisujacy.{index}.imie_nazwisko"], expected)
        self.assertEqual(apply_signatures(document, value, self.classes["pelnomocnictwo"], None), ({}, {}))



class MockPage:
    def get_size(self):
        return 595, 842

    def render(self, *, rotation, **_options):
        return SimpleNamespace(buffer=bytes([rotation // 90]), width=1, height=1,
                               n_channels=1, stride=1, close=lambda: None)

    def close(self):
        pass


class MockPdf:
    def __init__(self, _path):
        pass

    def __getitem__(self, _page):
        return MockPage()

    def close(self):
        pass


class MockOcr:
    def __init__(self, attempts, *, skip_layout=False, short_last=False):
        self.attempts = attempts
        self.skip_layout = skip_layout
        self.short_last = short_last

    def __enter__(self):
        return self

    def __exit__(self, *_error):
        pass

    def SetVariable(self, *_parameters):
        pass

    def SetImageBytes(self, pixels, *_dimensions):
        self.rotation = pixels[0]

    def GetUTF8Text(self):
        self.attempts.append(("text", self.rotation))
        if self.short_last:
            return PREAMBLE if self.rotation == 0 else "skan"
        return PREAMBLE if self.rotation == 1 else "skan"

    def MeanTextConf(self):
        if self.short_last:
            return 54
        return 95 if self.rotation == 1 else 30

    def GetTSVText(self, _page):
        self.attempts.append(("tsv", self.rotation))
        if self.skip_layout:
            raise RuntimeError("test: usterka pustej warstwy")
        return footer_tsv(f"wybrany {self.rotation}")


class OcrLayoutTransportTest(unittest.TestCase):
    def test_retains_layout_from_selected_orientation_without_an_extra_read(self):
        with TemporaryDirectory() as folder:
            pdf = Path(folder) / "scan.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=595, height=842)
            writer.write(pdf)
            attempts = []
            ocr = LocalOCR(MockPdf, lambda **_: MockOcr(attempts), Path(folder))
            document, ocr_pages = read_pdf(pdf, ocr)
            self.assertEqual(ocr_pages, [1])
            self.assertEqual(document.ocr_layout_tsv, footer_tsv("wybrany 1"))
            self.assertEqual(attempts, [("text", 0), ("tsv", 0), ("text", 1), ("tsv", 1)])

            attempts.clear()
            legacy = list(ocr.oriented_pages(pdf, 1))
            self.assertEqual(legacy, [(0, PREAMBLE, 90)])
            self.assertEqual(attempts, [("text", 0), ("text", 1)])

            attempts.clear()
            broken_layout = LocalOCR(MockPdf, lambda **_: MockOcr(attempts, skip_layout=True), Path(folder))
            without_layout, ocr_pages = read_pdf(pdf, broken_layout)
            self.assertEqual(ocr_pages, [1])
            self.assertIsNone(without_layout.ocr_layout_tsv)
            self.assertEqual(without_layout.text, document.text)

            attempts.clear()
            fallback = LocalOCR(MockPdf, lambda **_: MockOcr(attempts, short_last=True), Path(folder))
            fallback_doc, _ = read_pdf(pdf, fallback)
            self.assertEqual(fallback_doc.ocr_layout_tsv, footer_tsv("wybrany 0"))
            self.assertEqual(attempts, [("text", 0), ("tsv", 0), ("text", 1), ("text", 3), ("text", 2)])


if __name__ == "__main__":
    unittest.main()
