"""Sprawdziany zamrożonej kwalifikacji pól, wyłącznie na fikcyjnych danych."""
import json
from copy import deepcopy
from unittest import TestCase

from odwolania2json.__main__ import json_bytes
from odwolania2json.model import load_classes
from odwolania2json.review import IDENTITY, REPORT_VERSION, config_digest, digest, extractor_revision
from operator_panel.__main__ import (FIELD_CONFIG_SHA256, FIELD_OCR_REVISION, FIELD_TEXT_REVISION,
                                    TEXT_EVIDENCE_MEASUREMENT, eligible_fields)

AMOUNT = "przelew_bankowy.kwota"
DATE = "przelew_bankowy.data_operacji"


def fixture(source="text", *, bank=None):
    result = {"przelew_bankowy": bank if bank is not None else {"kwota": 46.2, "data_operacji": "2026-03-27"}}

    def quote(rule, text, start):
        return {"page": 2, "source": source, "rule": rule, "precision": "snippet", "snippet": text,
                "span": {"start": start, "end": start + len(text)}}

    record = {
        "report_version": REPORT_VERSION, "class": "przelew", "status": "ok",
        "input": "fikcja.pdf", "pdf_sha256": "f" * 64, "output_sha256": digest(json_bytes(result)),
        "config_sha256": FIELD_CONFIG_SHA256,
        "extractor_revision": FIELD_OCR_REVISION if source == "ocr" else FIELD_TEXT_REVISION,
        "review": {"status": "review_required", "profile": "przelew",
                   "reasons": [{"code": "profile_not_verified"}]},
        "review_status": "review_required", "decision": None,
        "pages": [{"page": 1, "status": "readable", "source": "text"},
                  {"page": 2, "status": "readable", "source": source}],
        "ocr_pages": [2] if source == "ocr" else [],
        "signals": [{"page": 2, "rule": rule} for rule in
                    ("nagłówek_przelewu", "data_operacji", "kwota_operacji")],
        "fields": {AMOUNT: quote("kwota_operacji", "46,20", 39),
                   DATE: quote("data_transakcji", "27.03.2026", 12)},
    }
    record["review_id"] = review_id(record)
    return record, result


def review_id(record):
    return digest(json.dumps({k: record[k] for k in IDENTITY}, sort_keys=True).encode())


class FieldEvidenceTest(TestCase):
    def test_pins_match_actual_class_configuration_and_revisions(self):
        config = config_digest(load_classes())
        self.assertEqual(config, FIELD_CONFIG_SHA256)
        self.assertEqual(extractor_revision(config, False), FIELD_TEXT_REVISION)
        self.assertEqual(extractor_revision(config, True), FIELD_OCR_REVISION)
        self.assertNotEqual(extractor_revision(config, True, ocr_page_budget=1), FIELD_OCR_REVISION)
        self.assertNotEqual(extractor_revision(config, True, verifier_profile="foreign"), FIELD_OCR_REVISION)
        if TEXT_EVIDENCE_MEASUREMENT is not None:
            self.assertIsInstance(TEXT_EVIDENCE_MEASUREMENT["strong"], bool)
            self.assertLessEqual(0, TEXT_EVIDENCE_MEASUREMENT["correct"])
            self.assertLessEqual(TEXT_EVIDENCE_MEASUREMENT["correct"], TEXT_EVIDENCE_MEASUREMENT["total"])

    def test_independent_groups_even_while_document_requires_review(self):
        for source in ("text", "ocr"):
            with self.subTest(source=source):
                record, result = fixture(source)
                original = deepcopy((record, result))
                self.assertEqual(eligible_fields(record, result), {AMOUNT: source, DATE: source})
                self.assertEqual((record, result), original)

    def test_old_stale_or_replaced_result_must_be_reinspected(self):
        for change in ({"report_version": 0}, {"review_status": "stale"}, {"review_id": None},
                       {"extractor_revision": "sha256:" + "f" * 64}, {"review_status": "unavailable"}):
            record, result = fixture()
            self.assertEqual(eligible_fields({**record, **change}, result), {})
        record, result = fixture()
        del record["review_status"]
        self.assertEqual(eligible_fields(record, result), {})
        record, result = fixture()
        result["przelew_bankowy"]["kwota"] = 18.5
        self.assertEqual(eligible_fields(record, result), {})

    def test_foreign_configuration_and_restored_default(self):
        record, result = fixture()
        self.assertEqual(eligible_fields({**record, "config_sha256": "f" * 64}, result), {})
        self.assertEqual(eligible_fields(record, result), {AMOUNT: "text", DATE: "text"})
        record["class"] = "odwolanie"
        self.assertEqual(eligible_fields(record, result), {})

    def test_both_signals_and_matching_readable_source_on_the_evidence_page(self):
        record, result = fixture()
        record["signals"][-1]["page"] = 1
        self.assertEqual(eligible_fields(record, result), {DATE: "text"})
        record["signals"][0]["page"] = 1
        self.assertEqual(eligible_fields(record, result), {})
        record, result = fixture("ocr")
        record["pages"][1]["source"] = "text"
        self.assertEqual(eligible_fields(record, result), {})
        record, result = fixture("ocr")
        record["ocr_pages"] = []
        self.assertEqual(eligible_fields(record, result), {})
        record, result = fixture()
        record["pages"].append(deepcopy(record["pages"][1]))
        self.assertEqual(eligible_fields(record, result), {})
        record, result = fixture()
        record["pages"][1]["status"] = "partial"
        self.assertEqual(eligible_fields(record, result), {})

    def test_field_blockers_and_class_conflict(self):
        record, result = fixture()
        record["review"]["reasons"] += [{"code": "field_evidence_conflict", "field": AMOUNT}]
        self.assertEqual(eligible_fields(record, result), {DATE: "text"})
        record["review"]["reasons"] += [{"code": "classification_conflict", "page": 1}]
        self.assertEqual(eligible_fields(record, result), {})

    def test_quote_span_operation_and_normalization(self):
        for changes in ({"rule": "ocr_wiersz_kwoty"}, {"precision": "page"}, {"span": {"start": 1, "end": 5}},
                        {"snippet": "46,21"}, {"snippet": "opłata 46,20", "span": {"start": 0, "end": 12}},
                        {"page": True}):
            with self.subTest(changes=changes):
                record, result = fixture()
                record["fields"][AMOUNT].update(changes)
                self.assertEqual(eligible_fields(record, result), {DATE: "text"})
        record, result = fixture(bank={"kwota": True, "data_operacji": "2026-02-31"})
        self.assertEqual(eligible_fields(record, result), {})
        record, result = fixture()
        record["fields"][AMOUNT] = [record["fields"][AMOUNT]] * 2
        self.assertEqual(eligible_fields(record, result), {DATE: "text"})

    def test_human_decision_remains_separate_and_corrected_field_loses_eligibility(self):
        record, result = fixture()
        record["decision"] = {"action": "accepted", "review_id": record["review_id"],
                              **{k: record[k] for k in IDENTITY}}
        record["review_status"] = "resolved"
        self.assertEqual(eligible_fields(record, result), {AMOUNT: "text", DATE: "text"})
        record["decision"].update(action="corrected", field=AMOUNT)
        self.assertEqual(eligible_fields(record, result), {DATE: "text"})
        record["decision"]["review_id"] = "f" * 64
        self.assertEqual(eligible_fields(record, result), {})
