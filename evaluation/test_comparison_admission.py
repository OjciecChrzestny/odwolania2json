"""Controls for the source seal and the decision to admit a comparison cohort."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from evaluation.compare_once import checked_cohorts
from evaluation.control_protocol_06 import write_json

BASE = "96f88b6fa61581ab54d35494cc59f43dc248bc01"
CLASSES = ("odwolanie", "pelnomocnictwo", "przelew")


class ComparisonAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.runtime = {"prefix": "/usr", "base": "/usr"}
        self.spec = {"mode": "synthetic", "cohorts": {}}
        self.proof = {"version": 1, "custodian": "01", "sealed_utc": "2026-11-21T23:00:00Z",
                      "base_sha": BASE, "control_inventory": {"pdf_sha256": ["a" * 64], "source_sha256": [],
                                                               "template_families": ["control-family"]},
                      "cohorts": {}}
        for cohort in ("known_128", "blind_full_cases", "blind_transfers", "page_review"):
            self.skip(cohort, "Brak przygotowanego syntetycznego zbioru dla tej kohorty.")
        self.set_full_cases()
        self.proof_path = self.root / "01-pieczec.json"

    def skip(self, cohort, reason):
        entry = {"status": "unavailable", "reason": reason}
        self.spec["cohorts"][cohort] = dict(entry)
        self.proof["cohorts"][cohort] = dict(entry)

    def set_full_cases(self, count=10):
        rows, origins, cases = [], [], {}
        for number in range(count):
            case_id = f"cas-{number:02}"
            cases[case_id] = {"source_case_id": f"archive:case:{number}", "authentic": True}
            kinds = (*CLASSES, "negative") if number == 0 else CLASSES
            for klass in kinds:
                name = f"{case_id}/{klass}.pdf"
                pdf_hash = hashlib.sha256(name.encode()).hexdigest()
                rows.append({"input": name, "pdf": name, "reference": None if klass == "negative" else f"{name}.json",
                             "class": klass, "sha256": pdf_hash})
                origins.append({"input": name, "pdf_sha256": pdf_hash, "source_sha256": pdf_hash,
                                "case_id": case_id, "source_document_id": f"archive:{name}",
                                "template_family": "blind-full-family"})
        self.record_manifest("blind_full_cases", rows, origins, cases=cases)

    def record_manifest(self, name, rows, origins, **extras):
        manifest = self.root / (name + ".json")
        sha = write_json(manifest, {"documents": rows})
        self.spec["cohorts"][name] = {"status": "ready", "dataset": str(self.root), "manifest": str(manifest),
                                      "manifest_sha256": sha, "labels": "synthetic"}
        self.proof["cohorts"][name] = {"status": "ready", "manifest_sha256": sha, "labels": "synthetic",
                                       "documents": origins, **extras}

    def bind(self):
        sha = write_json(self.proof_path, self.proof)
        self.spec["source_seal"] = {"path": str(self.proof_path), "sha256": sha}

    def verify(self):
        self.bind()
        _, _, result, ready = checked_cohorts(self.spec, BASE, self.runtime)
        return result, ready

    def test_omission_is_explicit_and_full_cases_are_admitted_with_unique_sources(self):
        result, ready = self.verify()
        self.assertEqual(set(ready), {"blind_full_cases"})
        self.assertEqual(result["blind_full_cases"]["authenticated_case_ids"], 10)
        self.assertEqual(result["blind_full_cases"]["documents"], 31)
        self.assertEqual(result["page_review"], self.spec["cohorts"]["page_review"])
        self.assertNotIn("manifest", result["blind_transfers"])

    def test_duplicate_case_aliases_are_rejected(self):
        cases = self.proof["cohorts"]["blind_full_cases"]["cases"]
        cases["cas-09"]["source_case_id"] = cases["cas-08"]["source_case_id"]
        with self.assertRaisesRegex(ValueError, "zdublowane sprawy"):
            self.verify()

    def test_split_copies_do_not_count_as_two_cases(self):
        docs = self.proof["cohorts"]["blind_full_cases"]["documents"]
        first = next(row for row in docs if row["case_id"] == "cas-00")
        second = next(row for row in docs if row["case_id"] == "cas-01")
        self.assertNotEqual(first["pdf_sha256"], second["pdf_sha256"])
        second["source_sha256"] = first["source_sha256"]
        with self.assertRaisesRegex(ValueError, "hash powtórzony między kohortami lub sprawami"):
            self.verify()

    def test_disallowed_control_template_family_is_rejected(self):
        docs = self.proof["cohorts"]["blind_full_cases"]["documents"]
        docs[0]["template_family"] = "control-family"
        with self.assertRaisesRegex(ValueError, "rodziny szablonu z ewidencji kontrolnej"):
            self.verify()

    def test_different_pdf_bytes_do_not_override_a_known_source_hash(self):
        docs = self.proof["cohorts"]["blind_full_cases"]["documents"]
        docs[0]["source_sha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "hash powtarza dokument z ewidencji kontrolnej"):
            self.verify()

    def test_source_seal_tampered_after_binding_is_rejected(self):
        self.bind()
        self.proof_path.write_bytes(self.proof_path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "Niezgodny SHA-256 pieczęci źródeł 01"):
            checked_cohorts(self.spec, BASE, self.runtime)

    def test_valid_seal_hash_with_different_measurement_manifest_is_rejected(self):
        self.proof["cohorts"]["blind_full_cases"]["manifest_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "manifest .* nie zgadza się z pieczęcią źródeł 01"):
            self.verify()

    def test_incomplete_cases_are_unavailable(self):
        name = "blind_full_cases"
        manifest = Path(self.spec["cohorts"][name]["manifest"])
        rows = json.loads(manifest.read_bytes())["documents"]
        meta = self.proof["cohorts"][name]
        rows.pop()
        self.record_manifest(name, rows, meta["documents"][:-1], cases=meta["cases"])
        result, ready = self.verify()
        self.assertNotIn(name, ready)
        self.assertIn("9/10", result[name]["reason"])

    def test_missing_page_labels_are_unavailable(self):
        rows = [{"input": "page.pdf", "pdf": "page.pdf", "class": "negative",
                 "reference": None, "sha256": "e" * 64, "pages": [{"page": 1, "status": "readable"}]}]
        origins = [{"input": "page.pdf", "pdf_sha256": "e" * 64, "source_sha256": "e" * 64,
                    "template_family": "pages-only", "source_document_id": "pages:page.pdf", "page_count": 2}]
        self.record_manifest("page_review", rows, origins)
        result, ready = self.verify()
        self.assertNotIn("page_review", ready)
        self.assertIn("niezależnej listy ocen stron", result["page_review"]["reason"])

    def test_hash_overlap_between_cohorts_is_rejected(self):
        full = self.proof["cohorts"]["blind_full_cases"]["documents"][0]
        pdf_hash = full["pdf_sha256"]
        rows = [{"input": "same.pdf", "pdf": "same.pdf", "class": "negative",
                 "reference": None, "sha256": pdf_hash, "pages": [{"page": 1, "status": "readable"}]}]
        origins = [{"input": "same.pdf", "pdf_sha256": pdf_hash, "source_sha256": "f" * 64,
                    "template_family": "pages-only", "source_document_id": "other:duplicate", "page_count": 1}]
        self.record_manifest("page_review", rows, origins)
        with self.assertRaisesRegex(ValueError, "hash powtórzony między kohortami lub sprawami"):
            self.verify()

    def test_independent_blind_cohorts_report_shared_non_control_families(self):
        rows = [{"input": "separate.pdf", "pdf": "separate.pdf", "class": "negative",
                 "reference": None, "sha256": "e" * 64, "pages": [{"page": 1, "status": "readable"}]}]
        origins = [{"input": "separate.pdf", "pdf_sha256": "e" * 64, "source_sha256": "e" * 64,
                    "template_family": "blind-full-family", "source_document_id": "other:separate", "page_count": 1}]
        self.record_manifest("page_review", rows, origins)
        result, ready = self.verify()
        self.assertIn("page_review", ready)
        self.assertEqual(result["page_review"]["shared_template_families"], ["blind-full-family"])

    def test_bound_manifest_on_disk_cannot_change(self):
        self.bind()
        path = Path(self.spec["cohorts"]["blind_full_cases"]["manifest"])
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "SHA-256 manifestu niezgodny"):
            checked_cohorts(self.spec, BASE, self.runtime)


if __name__ == "__main__":
    unittest.main()
