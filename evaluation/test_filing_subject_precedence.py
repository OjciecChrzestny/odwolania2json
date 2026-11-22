"""Guard the first subject over the secondary W0 rule and preserve original A3."""
import unittest

from odwolania2json.__main__ import _DEFAULT_EXTRACT_DOCUMENT
from odwolania2json.extract import extract
from odwolania2json.filing_reason import FILING_RULE, filing_extractor
from odwolania2json.model import Document, load_classes


HEADER = "Krajowa Izba Odwoławcza\nZamawiający: Fikcyjna jednostka\n"
FILING = (
    "Wnoszę odwołanie wobec treści Specyfikacji Warunków Zamówienia (SWZ) opublikowanej "
    "przez zamawiającego, która wprowadza projektowane postanowienia umowy."
)


class FilingSubjectPrecedenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def reason(self, value):
        return value["OdwolanieKIO"]["czynnosc_powod_id"]

    def test_foreign_title_attributed_in_prose_leaves_the_original_fallback(self):
        doc = Document.from_pages((HEADER + "Z pisma innego wykonawcy przytaczamy:\n"
            "ODWOŁANIE\nod czynności i zaniechań Zamawiającego\nwobec:\n"
            "1. projektowanych postanowień umowy.",))
        before = extract(doc, self.classes)
        self.assertTrue(before[1]["first_allegation"]["fallback"])
        self.assertEqual(_DEFAULT_EXTRACT_DOCUMENT(doc, self.classes), before)

    def test_direct_first_subject_takes_precedence_over_later_rule_from_w0(self):
        doc = Document.from_pages((HEADER + "ODWOŁANIE", FILING))
        old_value, old_report = filing_extractor("rule")(doc, self.classes)
        self.assertEqual(self.reason(old_value), 12)
        self.assertEqual(old_report["first_allegation"]["rule"], FILING_RULE)

        value, report = _DEFAULT_EXTRACT_DOCUMENT(doc, self.classes)
        self.assertEqual(self.reason(value), 4)
        self.assertEqual(value["OdwolanieKIO"]["czynnosc_opis"],
                         self.classes["odwolanie"]["reasons"]["descriptions"]["4"])
        source = report["first_allegation"]
        self.assertEqual(source["page"], 2)
        self.assertFalse(source["fallback"])
        self.assertTrue(source["source_excerpt"].startswith("treści Specyfikacji"))
        self.assertNotIn("projektowane", source["source_excerpt"])
        start = doc.starts[1][0]
        self.assertEqual(doc.text[start + source["source_span"]["start"]:start + source["source_span"]["end"]],
                         source["source_excerpt"])

    def test_original_a3_decision_is_preserved_even_with_a_different_filing_subject(self):
        doc = Document.from_pages((HEADER + "ODWOŁANIE\n" + FILING
                                   + "\nZarzut I: Zaskarżam decyzję o wykluczeniu wykonawcy.",))
        before = extract(doc, self.classes)
        self.assertEqual(self.reason(before[0]), 3)
        self.assertFalse(before[1]["first_allegation"]["fallback"])
        self.assertEqual(_DEFAULT_EXTRACT_DOCUMENT(doc, self.classes), before)
