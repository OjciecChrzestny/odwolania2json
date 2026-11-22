import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from odwolania2json.__main__ import process

from odwolania2json.extract import extract
from odwolania2json.filing_reason import filing_extractor, select_filing, select_filing_evidence
from odwolania2json.model import Document, load_classes

HEADER = (
    "Krajowa Izba Odwoławcza\nOdwołujący: Fikcyjna spółka\n"
    "Zamawiający: Fikcyjna gmina\nODWOŁANIE"
)
LIST = ("Na podstawie art. 513 Pzp wnoszę odwołanie wobec:\n"
        "1. Czynności unieważnienia postępowania;\n"
        "2. Zaniechania odrzucenia oferty.\n"
        "Czynności Zamawiającego zarzucam naruszenie:\n1) Art. 226 Pzp przez zaniechanie odrzucenia oferty.")


class FilingTests(unittest.TestCase):
    def setUp(self):
        self.classes = load_classes()
        self.config = self.classes["odwolanie"]

    def run_rule(self, pages):
        result, record = filing_extractor()(Document.from_pages([HEADER, *pages]), self.classes)
        decision = result["OdwolanieKIO"]
        self.assertIs(type(decision["czynnosc_powod_id"]), int)
        self.assertEqual(self.config["reasons"]["descriptions"][str(decision["czynnosc_powod_id"])],
                         decision["czynnosc_opis"])
        return decision["czynnosc_powod_id"], record["first_allegation"]

    def test_first_filing_is_distinct_from_later_items_and_articles(self):
        reason, evidence = self.run_rule([LIST])
        self.assertEqual((reason, evidence["page"], evidence["fallback"]), (9, 2, False))

    def test_future_remedy_does_not_supply_the_present_act(self):
        reason, evidence = self.run_rule(
            ["Wnoszę odwołanie wobec ochrony interesu.\nWnoszę o unieważnienie postępowania."])
        self.assertEqual((reason, evidence["fallback"]), (11, True))
        reason, _ = self.run_rule(["Wnoszę o wybór oferty.\n" + LIST])
        self.assertEqual(reason, 9)

    def test_foreign_quotation_cannot_supply_a_filing(self):
        for quote in ('Wykonawca wskazał: „Wnoszę odwołanie od odrzucenia oferty.”',
                      'Cytat:\nWnoszę odwołanie od odrzucenia oferty.'):
            with self.subTest(quote=quote):
                document = Document.from_pages([HEADER, quote])
                self.assertIsNone(select_filing(document, self.config))
                self.assertEqual(filing_extractor()(document, self.classes),
                                 extract(document, self.classes))

    def test_normal_process_finds_the_first_subject_in_a_filing_title(self):
        page = HEADER + (
            "\nod czynności Zamawiającego\nwobec:\n"
            "1. projektowanych postanowień umowy;\n2. wyboru oferty."
        )
        with TemporaryDirectory() as working:
            root = Path(working)
            source = root / "input"
            source.mkdir()
            (source / "pismo.pdf").write_bytes(b"synthetic reader fixture")
            diagnostic = root / "diagnostics.json"

            def read_document(path, engine, *, classes):
                return Document.from_pages([page]), []

            status = process(source, root / "output", self.classes, diagnostic,
                             read_document=read_document)
            self.assertEqual(status, 0)
            value = json.loads((root / "output/pismo.json").read_text())
            self.assertEqual(value["OdwolanieKIO"]["czynnosc_powod_id"], 12)
            evidence = json.loads(diagnostic.read_text())["documents"][0]["first_allegation"]
            self.assertEqual(evidence["page"], 1)
            self.assertEqual(evidence["rule"], "przedmiot_pierwszej_zaskarżonej_czynności")
            self.assertEqual(evidence["source_excerpt"], "projektowanych postanowień umowy")

    def test_filing_item_can_start_on_the_next_page(self):
        reason, evidence = self.run_rule(
            ["Na podstawie art. 513 Pzp wnoszę odwołanie wobec następujących czynności:",
             "1. Wykluczenia wykonawcy;\n2. Wyboru oferty."])
        self.assertEqual((reason, evidence["page"]), (3, 3))

    def test_numbered_list_resumes_after_page_furniture(self):
        reason, evidence = self.run_rule(["Wnoszę odwołanie wobec:\nAdres korespondencyjny",
                                          "Logo wydawcy\n1. Wykluczenia wykonawcy."])
        self.assertEqual((reason, evidence["page"]), (3, 3))

    def test_resolved_a3_does_not_reach_ranker(self):
        source = "Wnoszę odwołanie wobec:\n1. Czynności unieważnienia postępowania."
        document = Document.from_pages([HEADER, source, "Zarzut nr 1: wybór oferty."])
        hook = filing_extractor("rank", ranker=lambda _: self.fail("protected A3 reached ranker"))
        output, diagnostic = hook(document, self.classes)
        self.assertEqual(output["OdwolanieKIO"]["czynnosc_powod_id"], 2)
        self.assertFalse(diagnostic["first_allegation"]["fallback"])

    def test_ranker_errors_and_invalid_types_preserve_fallback(self):
        def failure(_):
            raise OSError("controlled")
        source = Document.from_pages([HEADER, LIST])
        for ranker in (failure, lambda _: "9", lambda _: True, lambda _: 13):
            hook = filing_extractor("rank", ranker=ranker)
            output, diagnostic = hook(source, self.classes)
            self.assertEqual(output["OdwolanieKIO"]["czynnosc_powod_id"], 11)
            self.assertTrue(diagnostic["first_allegation"]["fallback"])

    def test_explicit_second_number_is_not_promoted(self):
        source = Document.from_pages([HEADER, "Wnoszę odwołanie wobec:\n2. Odrzucenia oferty."])
        self.assertIsNone(select_filing(source, self.config))

    def test_foreign_block_keeps_ownership_until_explicit_end(self):
        quote = ("Treść przytoczonego\nodwołania innego wykonawcy:\n"
                 "Początek wypowiedzi.\nWnoszę odwołanie od odrzucenia oferty.")
        for text, reason, fallback in (
            (quote, 11, True),
            (quote + "\nKoniec przytoczenia.\nWnoszę odwołanie od wykluczenia wykonawcy.", 3, False),
        ):
            with self.subTest(fallback=fallback):
                code, evidence = self.run_rule([text])
                self.assertEqual((code, evidence["fallback"]), (reason, fallback))

    def test_inline_remedy_is_not_an_act(self):
        demand = ("Wnoszę odwołanie wobec naruszenia mojego interesu "
                  "i w konsekwencji żądam unieważnienia postępowania.")
        source = Document.from_pages([HEADER, demand])
        self.assertIsNone(select_filing(source, self.config))
        reason, evidence = self.run_rule([demand])
        self.assertEqual((reason, evidence["fallback"]), (11, True))
        positive = "Wnoszę odwołanie od wykluczenia wykonawcy i w konsekwencji żądam unieważnienia postępowania."
        reason, evidence = self.run_rule([positive])
        self.assertEqual((reason, evidence["page"]), (3, 2))

    def test_all_profiles_use_the_decisive_page(self):
        source = Document.from_pages([
            HEADER,
            "Wnoszę odwołanie od decyzji zamawiającego dotyczącej oferty wykonawcy, polegającej na",
            "odrzuceniu oferty.",
        ])
        shared = select_filing_evidence(source, self.config)
        self.assertEqual((shared.fragment.page, shared.required_reason_id), (3, 1))
        self.assertEqual(shared.quote.text, "odrzuceniu oferty.")
        for hook in (filing_extractor(), filing_extractor("lexical"),
                     filing_extractor("rank", ranker=lambda text: 1)):
            output, diagnostic = hook(source, self.classes)
            self.assertEqual(output["OdwolanieKIO"]["czynnosc_powod_id"], 1)
            self.assertEqual(diagnostic["first_allegation"]["page"], 3)
            for field in ("czynnosc_powod_id", "czynnosc_opis"):
                self.assertEqual(diagnostic["fields"][f"OdwolanieKIO.{field}"]["page"], 3)
        output, diagnostic = filing_extractor("rank", ranker=lambda text: 7)(source, self.classes)
        self.assertEqual(output["OdwolanieKIO"]["czynnosc_powod_id"], 11)
        self.assertTrue(diagnostic["first_allegation"]["fallback"])

    def test_action_split_across_two_pages_cannot_support_one_page(self):
        source = Document.from_pages([
            HEADER, "Wnoszę odwołanie wobec zaniechania", "odrzucenia oferty.",
        ])
        self.assertIsNone(select_filing(source, self.config))
        outcome, diagnostic = filing_extractor(
            "rank", ranker=lambda text: self.fail("ranker called without a single-page witness")
        )(source, self.classes)
        self.assertEqual(outcome["OdwolanieKIO"]["czynnosc_powod_id"], 11)
        self.assertTrue(diagnostic["first_allegation"]["fallback"])

    def test_single_page_ranked_evidence_without_a_rule_match_is_retained(self):
        source = Document.from_pages([
            HEADER,
            "Wnoszę odwołanie wobec treści specyfikacji warunków zamówienia opublikowanej przez zamawiającego.",
        ])
        selection = select_filing_evidence(source, self.config)
        self.assertIsNone(selection.rule_reason_id)
        self.assertIsNone(selection.required_reason_id)
        self.assertEqual(selection.fragment.page, 2)
        value, diagnostic = filing_extractor("rank", ranker=lambda text: 4)(source, self.classes)
        self.assertEqual(value["OdwolanieKIO"]["czynnosc_powod_id"], 4)
        self.assertEqual((diagnostic["first_allegation"]["page"], diagnostic["first_allegation"]["fallback"]),
                         (2, False))
