import tempfile
import unittest
from pathlib import Path

from proba import checked_stage, quality_report, stage_files, write_json


class ProbaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.sha = "a" * 40
        self.quality = {
            "sha": self.sha, "zbior": "niezalezny", "sha256_manifestu": "b" * 64,
            "liczba_pdf": 3, "tp": 3, "fp": 1, "fn": 3,
            "valid_run": False, "valid_contract": True,
        }

    def test_quality_preserves_invalid_run_and_computes_micro_f1(self):
        path = self.work / "jakosc.json"
        write_json(path, self.quality)
        report = quality_report(path, self.sha)
        self.assertAlmostEqual(report["micro_f1"], 0.6)
        self.assertIs(report["valid_run"], False)
        self.assertIs(report["valid_contract"], True)

    def test_quality_rejects_different_revision(self):
        path = self.work / "jakosc.json"
        write_json(path, self.quality)
        with self.assertRaisesRegex(ValueError, "SHA pomiaru jakości"):
            quality_report(path, "e" * 40)

    def test_stage_rejects_changed_output_and_mixed_runtime(self):
        stage = "przelew"
        output = self.work / "domyslne/output/doc_01.json"
        diagnostics = self.work / "domyslne/diagnostics/last-run.json"
        for path in (output, diagnostics):
            path.parent.mkdir(parents=True)
            write_json(path, {})
        identity = {"sha": self.sha, "tryb": "natywny"}
        record = {"rewizja": identity, "pliki": stage_files(self.work, stage)}
        write_json(self.work / f"czasy-{stage}.json", record)
        self.assertEqual(checked_stage(self.work, stage, identity), record)

        with self.assertRaisesRegex(ValueError, "Tożsamość etapu"):
            checked_stage(self.work, stage, {**identity, "tryb": "Docker --network none"})
        write_json(output, {"changed": True})
        with self.assertRaisesRegex(ValueError, "Pliki etapu"):
            checked_stage(self.work, stage, identity)
