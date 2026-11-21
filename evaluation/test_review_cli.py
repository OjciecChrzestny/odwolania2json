"""Próby kolejki na syntetycznych PDF-ach przez publiczne CLI."""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from odwolania2json.review import review_details

from test_baseline_a import ROOT, write_pdf


PDF = "sprawa/przelew.PDF"
NEGATIVE = "sprawa/protokol.pdf"
AMOUNT = "przelew_bankowy.kwota"
ACCOUNT = "przelew_bankowy.z_rachunku"
NUMBER = "05123456789012345678901216"
RECEIPT = "\n".join(["POTWIERDZENIE PRZELEWU", "Data operacji: 2026-01-02", "Kwota: 12,50 PLN",
                    f"Rach. debetowy: {NUMBER}", "Na rachunek: 00987654321098765432109876", "Numer transakcji: 0000123"])


class ReviewCliTest(unittest.TestCase):
    def setUp(self):
        work = TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.input = self.root / "wejście"
        self.output = self.root / "wyjście"
        self.report = self.root / "kontrola" / "raport.json"
        self.journal = self.report.with_suffix(".decisions.sqlite3")
        self.result = self.output / Path(PDF).with_suffix(".json")
        self.negative_result = self.output / Path(NEGATIVE).with_suffix(".json")
        write_pdf(self.input / PDF, RECEIPT)
        write_pdf(self.input / NEGATIVE, "Protokol omawia odwolanie oraz przelew i pelnomocnictwo.")
        self.cli()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", "-m", "odwolania2json", "--input", self.input, "--output", self.output,
             "--diagnostics", self.report, *args],
            cwd=self.root, env={**os.environ, "PYTHONPATH": str(ROOT)},
            text=True, encoding="utf-8", capture_output=True, timeout=15,
        )

    def cli(self, *args, code=0):
        run = self.run_cli(*args)
        self.assertEqual(run.returncode, code, run.stderr)
        return json.loads(run.stdout) if run.returncode == 0 and "review" in args else run.stderr

    def show(self, name=PDF):
        return self.cli("review", "show", name)

    def correct(self, review_id, field, value, code=0):
        return self.cli("review", "correct", PDF, "--expect", review_id,
                        "--field", field, "--value", json.dumps(value), code=code)

    def test_correct_missing_account_survives_restart_and_repeat(self):
        report_before = self.report.read_bytes()
        output_before = self.result.read_bytes()
        queue = self.cli("review", "list")
        self.assertEqual({row["input"] for row in queue}, {PDF, NEGATIVE})
        shown = self.show()
        evidence = shown["fields"][AMOUNT]
        self.assertEqual(evidence["page"], 1)
        self.assertTrue(evidence["rule"])
        self.assertEqual(evidence["source"], "text")
        self.assertIn(evidence["precision"], {"page", "snippet"})
        self.assertIsNone(shown["result"]["przelew_bankowy"]["z_rachunku"])

        review_id = shown["review_id"]
        self.assertIn("oczekiwany typ", self.correct(review_id, ACCOUNT, 123, code=2))
        self.assertIsNone(self.show()["decision"])
        decision = self.correct(review_id, ACCOUNT, NUMBER)
        self.assertEqual(decision["action"], "corrected")
        self.assertEqual(decision["field"], ACCOUNT)
        self.assertIsNone(decision["original_value"])
        self.assertEqual(decision["corrected_value"], NUMBER)
        self.assertEqual(decision["pdf_sha256"], sha256((self.input / PDF).read_bytes()).hexdigest())
        self.assertEqual(decision["output_sha256"], sha256(output_before).hexdigest())
        self.assertEqual(decision["extractor_revision"], shown["extractor_revision"])
        self.assertTrue(decision["decided_at"].endswith("+00:00"))

        self.assertEqual(self.correct(review_id, ACCOUNT, NUMBER), decision)
        self.assertIn("inna decyzja", self.correct(review_id, ACCOUNT, NUMBER[::-1], code=2))
        self.assertIn("inna decyzja", self.cli("review", "accept", PDF, "--expect", review_id, code=2))
        after_restart = self.show()
        self.assertEqual(after_restart["review_status"], "resolved")
        self.assertEqual(after_restart["decision"], decision)
        self.assertEqual([row["input"] for row in self.cli("review", "list")], [NEGATIVE])
        with closing(sqlite3.connect(self.journal)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM decisions").fetchone()[0], 1)
        self.assertEqual(self.report.read_bytes(), report_before)
        self.assertEqual(self.result.read_bytes(), output_before)
        self.assertEqual(self.negative_result.read_bytes(), b"")

    def test_old_acceptance_cannot_follow_changed_pdf_or_result(self):
        shown = self.show()
        first_id = shown["review_id"]
        accepted = self.cli("review", "accept", PDF, "--expect", first_id)
        self.assertEqual(self.show()["decision"], accepted)
        self.cli()
        self.assertEqual(self.show()["decision"], accepted)

        original_pdf = (self.input / PDF).read_bytes()
        original_result = self.result.read_bytes()
        self.result.write_bytes(original_result + b"\n")
        self.assertEqual(self.show()["review_status"], "stale")
        self.assertIsNone(self.show()["decision"])
        self.cli("review", "accept", PDF, "--expect", first_id, code=2)
        self.result.write_bytes(original_result)

        # Zmienione wejście o wciąż identycznych danych wyjściowych.
        write_pdf(self.input / PDF, RECEIPT + "\nDodatkowa stopka.")
        self.assertNotEqual((self.input / PDF).read_bytes(), original_pdf)
        self.assertEqual(self.show()["review_status"], "stale")
        self.cli()
        self.assertEqual(self.result.read_bytes(), original_result)
        self.assertIsNone(self.show()["decision"])
        self.cli("review", "accept", PDF, "--expect", first_id, code=2)

        # Zmieniona konfiguracja na tym samym PDF-ie daje rzeczywiście inny wynik.
        second = self.show()
        second_id = second["review_id"]
        self.cli("review", "accept", PDF, "--expect", second_id)
        configuration = self.root / "alternatywne-klasy"
        shutil.copytree(ROOT / "odwolania2json/classes", configuration)
        for path in configuration.glob("*.json"):
            data = json.loads(path.read_bytes())
            if data["class"] == "przelew":
                data["threshold"] = 10_000
                path.write_text(json.dumps(data), encoding="utf-8")
        self.cli("--config", configuration)
        self.assertEqual(self.result.read_bytes(), b"")
        latest = self.show()
        self.assertIsNone(latest["decision"])
        self.assertEqual(latest["pdf_sha256"], second["pdf_sha256"])
        self.assertNotEqual(latest["output_sha256"], second["output_sha256"])
        self.assertNotEqual(latest["extractor_revision"], second["extractor_revision"])
        self.cli("review", "accept", PDF, "--expect", second_id, code=2)

    def test_contract_report_includes_page_and_source_excerpt(self):
        report = json.loads(self.report.read_bytes())
        for record in report["documents"]:
            if record["input"] == PDF:
                snippet = "Kwota: 12,50 PLN"
                record["pages"] = [{"page": 1, "status": "readable", "reason": "native_text"}]
                record["fields"][AMOUNT] |= {"precision": "snippet", "snippet": snippet}
                record["review"]["reasons"] = [{"code": "ambiguous_account", "page": 1, "field": ACCOUNT}]
            else:
                record["review"] = {"status": "auto_accepted", "reasons": []}
        self.report.write_text(json.dumps(report), encoding="utf-8")
        self.assertEqual([item["input"] for item in self.cli("review", "list")], [PDF])
        shown = self.show()
        self.assertEqual(shown["pages"][0]["status"], "readable")
        self.assertEqual(shown["review"]["reasons"][0]["field"], ACCOUNT)
        self.assertEqual(shown["fields"][AMOUNT]["snippet"], "Kwota: 12,50 PLN")
        negative = self.show(NEGATIVE)
        self.assertEqual(negative["review_status"], "auto_accepted")
        self.cli("review", "accept", NEGATIVE, "--expect", negative["review_id"], code=2)

    def test_conflicting_parallel_decisions_have_one_winner(self):
        review_id = self.show()["review_id"]
        accept = ("review", "accept", PDF, "--expect", review_id)
        correct = ("review", "correct", PDF, "--expect", review_id,
                   "--field", ACCOUNT, "--value", json.dumps(NUMBER))
        with ThreadPoolExecutor(max_workers=2) as pool:
            runs = list(pool.map(lambda args: self.run_cli(*args), (accept, correct)))
        self.assertEqual(sorted(run.returncode for run in runs), [0, 2])
        winner = next(run for run in runs if run.returncode == 0)
        self.assertEqual(self.show()["decision"], json.loads(winner.stdout))
        with closing(sqlite3.connect(self.journal)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM decisions").fetchone()[0], 1)

    def test_missing_result_is_distinct_from_zero_byte_negative(self):
        broken = "sprawa/uszkodzony.pdf"
        (self.input / broken).write_bytes(b"bad PDF")
        self.cli(code=1)
        unavailable = self.show(broken)
        self.assertEqual(unavailable["review_status"], "unavailable")
        self.assertIsNone(unavailable["output_sha256"])
        self.assertIsNone(unavailable["review_id"])
        self.cli("review", "accept", broken, "--expect", "missing", code=2)

        negative = self.show(NEGATIVE)
        self.assertEqual(negative["output_sha256"], sha256(b"").hexdigest())
        self.assertEqual(negative["review_status"], "review_required")
        self.cli("review", "accept", NEGATIVE, "--expect", negative["review_id"])
        self.assertEqual(self.show(NEGATIVE)["decision"]["action"], "accepted")
        self.assertEqual(self.negative_result.read_bytes(), b"")


    def test_cli_adapter_passes_observation_evidence_and_value_to_policy(self):
        pages = [{"page": 1, "status": "readable", "reason": "native_text"},
                 {"page": 2, "status": "unassessed", "reason": "page_limit"}]
        quality = {"pages": pages, "status": "partial", "page_count": 2, "review_pages": [2]}
        document = SimpleNamespace(scan_quality=quality)
        evidence = {"page": 1, "rule": "amount", "precision": "snippet",
                    "snippet": "Kwota: 12,50 PLN", "source": "text"}
        record = {"class": "przelew", "status": "ok", "fields": {AMOUNT: evidence}, "ocr_pages": [2]}
        value = {"przelew_bankowy": {"kwota": 12.5}}
        policy = {"status": "review_required", "profile": "przelew",
                  "reasons": [{"code": "page_unassessed", "page": 2}]}
        with (patch("odwolania2json.review.decide_review", return_value=policy) as decide,
              patch("odwolania2json.review.with_field_sources", return_value={AMOUNT: evidence}) as sources):
            details = review_details(document, record, value, True)
        sources.assert_called_once_with({AMOUNT: evidence}, ocr_pages=[2])
        decide.assert_called_once_with("przelew", pages=pages, fields={AMOUNT: evidence}, value=value)
        self.assertEqual(details["scan_quality"], {"status": "partial", "page_count": 2, "review_pages": [2]})
        self.assertEqual(details["pages"], pages)
        self.assertEqual(details["review"], policy)

        failure = {"class": "read_error", "status": "read_error", "fields": {}}
        details = review_details(None, failure, None, False,
                                 read_error_quality={"pages": [], "reason": "pdf_open_failed"})
        self.assertEqual(details["scan_quality"]["reason"], "pdf_open_failed")
        self.assertEqual(details["review"]["status"], "review_required")

if __name__ == "__main__":
    unittest.main()
