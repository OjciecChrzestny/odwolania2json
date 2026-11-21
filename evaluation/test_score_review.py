"""Syntetyczny wzorzec i testy niezależnego miernika kontroli."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evaluation.score_review import score_review


def put_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False).encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def observations(states):
    return [{"page": page, "status": state, "reason": "synthetic_observation"}
            for page, state in enumerate(states, 1)]


def make_fixture(root):
    """Zapisuje niezależne, z góry policzone wejście i fikcyjny przebieg bez OCR."""
    dataset, output = root / "dataset", root / "output"
    manifest, diagnostics = root / "manifest.json", root / "last-run.json"
    cases = [
        ("negative", "auto_accepted", ("readable",), ("readable",)),
        ("swapped", "auto_accepted", ("readable", "unreadable"), ("readable", "readable")),
        ("wrong", "review_required", ("unreadable",), ("unreadable",)),
        ("correct", "review_required", ("readable",), ("unreadable",)),
    ]
    docs, records = [], []
    for case, state, gold_pages, observed_pages in cases:
        source, target = f"input/{case}.pdf", f"input/{case}.json"
        pdf, reference = f"pdf/{case}.pdf", f"labels/{case}.json"
        source_bytes = f"%PDF-1.7\nsynthetic review fixture: {case}\n".encode()
        (dataset / pdf).parent.mkdir(parents=True, exist_ok=True)
        (dataset / pdf).write_bytes(source_bytes)
        pdf_hash = hashlib.sha256(source_bytes).hexdigest()
        kind = "negative" if case == "negative" else "przelew"
        row = {"input": source, "pdf": pdf, "sha256": pdf_hash, "class": kind,
               "pages": observations(gold_pages)}
        result_file = output / target
        if kind == "negative":
            row["reference"] = None
            result_file.parent.mkdir(parents=True, exist_ok=True)
            result_file.write_bytes(b"")
            output_hash = hashlib.sha256(b"").hexdigest()
        else:
            gold = {"data_operacji": "2026-11-20", "kwota": 12.5, "tytul": "fikcja",
                    "numer_transakcji": "001", "z_rachunku": "1" * 26, "na_rachunek": "2" * 26}
            row["reference"] = reference
            row["reference_sha256"] = put_json(dataset / reference, {"przelew_bankowy": gold})
            pred = dict(gold)
            if case == "swapped":
                pred["z_rachunku"], pred["na_rachunek"] = pred["na_rachunek"], pred["z_rachunku"]
            if case == "wrong":
                pred["kwota"] = 25
            output_hash = put_json(result_file, {"przelew_bankowy": pred})
        docs.append(row)
        records.append({"input": source, "output": target, "pdf_sha256": pdf_hash,
                        "output_sha256": output_hash, "extractor_revision": "synthetic",
                        "report_version": 1, "class": kind,
                        "status": "negative" if kind == "negative" else "ok",
                        "pages": observations(observed_pages),
                        "review": {"status": state, "profile": kind, "reasons": []}})
    put_json(manifest, {"documents": docs})
    put_json(diagnostics, {"documents": records})
    return dataset, output, manifest, diagnostics


class ReviewScoreTest(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.args = make_fixture(Path(folder))
        self.dataset, self.output, self.manifest, self.diagnostics = self.args

    def read_diagnostics(self):
        return json.loads(self.diagnostics.read_bytes())

    def test_hand_calculated_counts_via_cli(self):
        completed = self.run_cli()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        overall = result["overall"]
        self.assertTrue(result["valid_run"])
        self.assertEqual(overall["decision_matrix"], {
            "correct": {"auto_accepted": 1, "review_required": 1, "without_decision": 0},
            "incorrect": {"auto_accepted": 1, "review_required": 1, "without_decision": 0},
        })
        self.assertEqual(overall["coverage"], {"numerator": 2, "denominator": 4, "rate": 0.5})
        self.assertEqual(overall["acceptance_accuracy"], {"numerator": 1, "denominator": 2, "rate": 0.5})
        self.assertEqual(overall["incorrect_review_rate"], {"numerator": 1, "denominator": 2, "rate": 0.5})
        self.assertEqual(overall["pages"], {
            "expected": 5, "missing": 0, "unreadable": 2, "detected": 1, "missed_unreadable": 1,
            "false_positives": 1, "unreadable_recall": {"numerator": 1, "denominator": 2, "rate": 0.5},
        })
        transfer = result["by_profile"]["przelew"]
        self.assertEqual(transfer["decision_matrix"]["incorrect"]["auto_accepted"], 1)
        self.assertEqual(transfer["acceptance_accuracy"], {"numerator": 0, "denominator": 1, "rate": 0.0})
        self.assertEqual(result["documents"][1]["fields"], {"tp": 4, "fp": 2, "fn": 2})
        field_score = result["field_score"]
        self.assertEqual((field_score["tp"], field_score["fp"], field_score["fn"]), (15, 3, 3))
        self.assertAlmostEqual(field_score["micro_f1"], 5 / 6)
        self.assertEqual(field_score["micro_f1_denominator"], 36)
        self.assertFalse(field_score["jury_compatibility_confirmed"])

    def run_cli(self):
        return subprocess.run(
            [sys.executable, "-B", "-m", "evaluation.score_review", str(self.dataset), str(self.output),
             "--manifest", str(self.manifest), "--diagnostics", str(self.diagnostics)],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )

    def test_no_auto_accepts_has_no_accuracy_denominator(self):
        report = self.read_diagnostics()
        for doc in report["documents"]:
            doc["review"]["status"] = "review_required"
        put_json(self.diagnostics, report)
        result = score_review(*self.args)
        self.assertTrue(result["valid_run"])
        overall = result["overall"]
        self.assertEqual(overall["coverage"], {"numerator": 0, "denominator": 4, "rate": 0.0})
        self.assertEqual(overall["acceptance_accuracy"], {"numerator": 0, "denominator": 0, "rate": None})
        self.assertEqual(overall["decision_matrix"]["incorrect"]["review_required"], 2)

    def test_missing_negative_output_is_wrong_despite_unchanged_field_counts(self):
        (self.output / "input/negative.json").unlink()
        completed = self.run_cli()
        self.assertEqual(completed.returncode, 1, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertFalse(result["valid_run"])
        self.assertEqual(result["overall"]["decision_matrix"]["incorrect"]["auto_accepted"], 2)
        self.assertEqual(result["overall"]["coverage"]["denominator"], 4)
        self.assertEqual(result["field_score"]["micro_f1"], 5 / 6)
        self.assertIn("brak pliku wynikowego", " ".join(result["errors"]))

    def test_duplicate_report_path_cannot_supply_an_arbitrary_decision(self):
        report = self.read_diagnostics()
        duplicate = dict(report["documents"][0], review={"status": "review_required"})
        report["documents"].append(duplicate)
        put_json(self.diagnostics, report)
        result = score_review(*self.args)
        self.assertFalse(result["valid_run"])
        overall = result["overall"]
        self.assertEqual(overall["decision_matrix"]["correct"]["without_decision"], 1)
        self.assertEqual(overall["coverage"], {"numerator": 1, "denominator": 4, "rate": 0.25})
        self.assertIn("powtórzona ścieżka", " ".join(result["errors"]))

    def test_forgotten_page_stays_in_unreadable_denominator(self):
        report = self.read_diagnostics()
        report["documents"][1]["pages"].pop()
        put_json(self.diagnostics, report)
        result = score_review(*self.args)
        self.assertFalse(result["valid_run"])
        pages = result["overall"]["pages"]
        self.assertEqual((pages["expected"], pages["missing"], pages["missed_unreadable"]), (5, 1, 1))
        self.assertEqual(pages["unreadable_recall"], {"numerator": 1, "denominator": 2, "rate": 0.5})
        self.assertIn("brak strony 2", " ".join(result["errors"]))

    def test_duplicate_page_and_missing_report_row_stay_visible(self):
        report = self.read_diagnostics()
        report["documents"][2]["pages"].append(report["documents"][2]["pages"][0])
        report["documents"].pop()
        put_json(self.diagnostics, report)
        result = score_review(*self.args)
        self.assertFalse(result["valid_run"])
        overall = result["overall"]
        self.assertEqual(overall["decision_matrix"]["correct"]["without_decision"], 1)
        self.assertEqual(overall["pages"]["unreadable_recall"], {"numerator": 0, "denominator": 2, "rate": 0.0})
        self.assertEqual(overall["pages"]["missing"], 2)
        self.assertIn("powtórzona strona 1", " ".join(result["errors"]))
        self.assertIn("brak rekordu diagnostyki", " ".join(result["errors"]))

    def test_missing_report_file_preserves_entire_manifest(self):
        self.diagnostics.unlink()
        result = score_review(*self.args)
        self.assertFalse(result["valid_run"])
        self.assertEqual(result["overall"]["coverage"]["denominator"], 4)
        self.assertEqual(result["overall"]["pages"]["missing"], 5)
        self.assertEqual(result["overall"]["decision_matrix"]["correct"]["without_decision"], 2)

    def test_stale_report_and_readability_cannot_credit_current_pdf(self):
        report = self.read_diagnostics()
        report["documents"][2]["pdf_sha256"] = "0" * 64
        report["documents"][0]["output_sha256"] = "1" * 64
        put_json(self.diagnostics, report)
        result = score_review(*self.args)
        self.assertFalse(result["valid_run"])
        overall = result["overall"]
        self.assertEqual(overall["decision_matrix"]["incorrect"]["auto_accepted"], 2)
        self.assertEqual(overall["pages"]["detected"], 0)
        errors = " ".join(result["errors"])
        self.assertIn("SHA-256 PDF-u", errors)
        self.assertIn("SHA-256 wyniku", errors)

    def test_wrong_class_is_attributed_to_the_profile_that_accepted_it(self):
        report = self.read_diagnostics()
        record = report["documents"][0]
        record.update({"class": "przelew", "status": "ok"})
        record["review"]["profile"] = "przelew"
        put_json(self.diagnostics, report)
        result = score_review(*self.args)
        self.assertEqual(result["by_profile"]["przelew"]["decision_matrix"]["incorrect"]["auto_accepted"], 2)
        self.assertNotIn("negative", result["by_profile"])

    def test_mixed_extractor_revisions_invalidate_the_run(self):
        report = self.read_diagnostics()
        report["documents"][0]["extractor_revision"] = "older"
        put_json(self.diagnostics, report)
        result = score_review(*self.args)
        self.assertFalse(result["valid_run"])
        self.assertEqual(result["extractor_revisions"], ["older", "synthetic"])
        self.assertIn("różne rewizje", " ".join(result["errors"]))

    def test_duplicate_manifest_path_rejects_unreliable_denominator(self):
        manifest = json.loads(self.manifest.read_bytes())
        manifest["documents"].append(manifest["documents"][0])
        put_json(self.manifest, manifest)
        completed = self.run_cli()
        self.assertEqual(completed.returncode, 2)
        self.assertIn("Powtórzona ścieżka wynikowa w manifeście", completed.stderr)


if __name__ == "__main__":
    unittest.main()
