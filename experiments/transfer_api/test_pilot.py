"""Regression checks for the actual synthetic response and deterministic API fallback."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.abc.adapters import sha256
from .run import run
from .scaleway import parse_answer


class TransferPilotTest(unittest.TestCase):
    def test_numeric_formats(self):
        rows = [{"row": 1}, {"row": 2}]
        for amount in ("17,42", "17.42"):
            self.assertEqual(parse_answer({"wiersz": 2, "wartosc": amount}, "kwota", rows), (2, 17.42))
        self.assertEqual(parse_answer({"wiersz": 1, "wartosc": "29.02.2024"}, "data_operacji", rows),
                         (1, "2024-02-29"))
        self.assertEqual(parse_answer({"wiersz": None, "wartosc": None}, "kwota", rows), (None, None))
        for field, row, value in (("kwota", 3, "17.42"), ("kwota", 2, "17,4.2"),
                                  ("data_operacji", 1, "30.02.2026")):
            with self.subTest(field=field, row=row, value=value), self.assertRaises(ValueError):
                parse_answer({"wiersz": row, "wartosc": value}, field, rows)

    def test_rate_limit_keeps_original_bytes_and_stops_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base, queue, dest = root / "A", root / "queue", root / "C"
            for path in (base / "input", base / "output", base / "diagnostics", queue):
                path.mkdir(parents=True)
            result = b'{"przelew_bankowy":{"kwota":null}}\n'
            pdf, png = b"synthetic pdf fixture", b"\x89PNG\r\n\x1a\nmasked fixture"
            panel = sha256(png)
            (queue / (panel + ".png")).write_bytes(png)
            names = ["doc1.json", "doc2.json"]
            entries = []
            for name in names:
                (base / "output" / name).write_bytes(result)
                (base / "input" / Path(name).with_suffix(".pdf")).write_bytes(pdf)
                entries.append({"output": name, "field": "kwota", "pdf_sha256": sha256(pdf),
                                "panel_sha256": panel, "rows": [{"row": 1, "labels": ["kwota"]}]})
            (base / "output/neg.json").write_bytes(b"")
            (base / "diagnostics/last-run.json").write_text(json.dumps(
                {"documents": [{"output": name, "fields": {}} for name in names + ["neg.json"]]}))
            (queue / "queue.json").write_text(json.dumps({
                "base_outputs": {**dict.fromkeys(names, sha256(result)), "neg.json": sha256(b"")},
                "candidates": entries}))
            with patch("experiments.transfer_api.run.load_token", return_value="fixture"), \
                 patch("experiments.transfer_api.run.read_field", return_value={
                     "http": 429, "outcome": "http_429"}) as reader:
                summary = run(base, queue, dest, max_calls=2)
            reader.assert_called_once()
            self.assertEqual(summary["calls"], 1)
            self.assertFalse(summary["valid_model_comparison"])
            for p in (dest / "output").iterdir():
                self.assertEqual(p.read_bytes(), (base / "output" / p.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
