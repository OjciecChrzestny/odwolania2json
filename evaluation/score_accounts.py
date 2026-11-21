"""Score ordered bank accounts and distinguish swapped roles from unread fields."""
import argparse
import json
from pathlib import Path

ROLES = ("z_rachunku", "na_rachunek")


def measure_accounts(dataset, output, manifest):
    fields = {role: dict(tp=0, fp=0, fn=0) for role in ROLES}
    counts = dict(documents=0, both_correct=0, complete_swaps=0, opposite_role_fields=0,
                  other_wrong=0, missing=0, unreadable_outputs=0)
    for row in manifest["documents"]:
        if row["class"] != "przelew":
            continue
        gold = json.loads((dataset / row["reference"]).read_bytes())["przelew_bankowy"]
        file = output / Path(row["input"]).with_suffix(".json")
        try:
            actual = json.loads(file.read_bytes())["przelew_bankowy"]
            if not isinstance(actual, dict):
                raise TypeError("expected an account object")
        except (OSError, ValueError, KeyError, TypeError):
            counts["unreadable_outputs"] += 1
            actual = {}
        expected = tuple(gold[key] for key in ROLES)
        got = tuple(actual.get(key) for key in ROLES)
        different = all(value is not None for value in expected) and expected[0] != expected[1]
        counts["documents"] += 1
        counts["both_correct"] += int(all(v is not None for v in expected) and got == expected)
        counts["complete_swaps"] += int(different and got == expected[::-1])
        for key, value, wanted, opposite in zip(ROLES, got, expected, reversed(expected)):
            if value is not None and value == wanted:
                fields[key]["tp"] += 1
            elif value != wanted:
                fields[key]["fp"] += int(value is not None)
                fields[key]["fn"] += int(wanted is not None)
                counts["missing"] += int(value is None)
                wrong_role = different and value == opposite
                counts["opposite_role_fields"] += int(wrong_role)
                counts["other_wrong"] += int(value is not None and not wrong_role)
    total = {key: sum(stats[key] for stats in fields.values()) for key in ("tp", "fp", "fn")}
    for stats in (*fields.values(), total):
        denom = 2 * stats["tp"] + stats["fp"] + stats["fn"]
        stats["micro_f1"] = 2 * stats["tp"] / denom if denom else None
    return {**counts, "fields": fields, "total": total}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(measure_accounts(args.dataset, args.output, json.loads(args.manifest.read_bytes())), indent=2))
