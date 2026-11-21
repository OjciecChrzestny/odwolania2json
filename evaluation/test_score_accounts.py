"""A swapped pair must score differently from two missing values."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from evaluation.score_accounts import measure_accounts


class OrderedAccountScoreTest(unittest.TestCase):
    def test_swapped_partial_wrong_and_empty_count_toward_the_same_denominator(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "expected.json").write_text(json.dumps({"przelew_bankowy": {"z_rachunku": "12", "na_rachunek": "34"}}))
            manifest = {"documents": []}
            for i, pair in enumerate((("34", "12"), ("12", "12"), ("56", None), None)):
                manifest["documents"].append({"class": "przelew", "input": f"{i}.pdf", "reference": "expected.json"})
                if pair:
                    obj = {"przelew_bankowy": dict(zip(("z_rachunku", "na_rachunek"), pair))}
                    (root / f"{i}.json").write_text(json.dumps(obj))
            metrics = measure_accounts(root, root, manifest)
            self.assertEqual((metrics["complete_swaps"], metrics["opposite_role_fields"]), (1, 3))
            self.assertEqual((metrics["missing"], metrics["other_wrong"], metrics["unreadable_outputs"]), (3, 1, 1))
            self.assertEqual(metrics["total"], dict(tp=1, fp=4, fn=7, micro_f1=2/13))
