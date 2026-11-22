"""Dwa źródła podpisu, przypisanie mocodawcy i zachowanie dowodu."""
from copy import deepcopy
import unittest

from odwolania2json.extract import extract
from odwolania2json.legal import Fragment, principal_blocks
from odwolania2json.model import Document, Extraction, load_classes
from odwolania2json.podpisy import SIGNATURE_RULE, add_confirmed_signatures

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



if __name__ == "__main__":
    unittest.main()
