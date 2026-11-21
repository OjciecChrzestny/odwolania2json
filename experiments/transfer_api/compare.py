"""Score previously saved A3 and Scaleway outputs; this module never calls an API."""
import argparse
from collections import Counter
import json
from pathlib import Path

from evaluation.check_outputs import check_outputs
from evaluation.score import load_object, score
from odwolania2json.model import DEFAULT_CONFIG, load_classes


def load(path):
    return json.loads(path.read_bytes())


def metrics(dataset, manifest, variant):
    docs = load(manifest)
    results = score(dataset, variant / "output", manifest)
    contract = check_outputs(variant / "output", docs, load(variant / "diagnostics/last-run.json"),
                             load_classes(DEFAULT_CONFIG))
    counts = {}
    negatives = 0
    complete = 0
    for entry in docs["documents"]:
        out = variant / "output" / Path(entry["input"]).with_suffix(".json")
        if not entry["reference"]:
            negatives += out.is_file() and out.stat().st_size == 0
            continue
        gold = load_object(dataset / entry["reference"])["przelew_bankowy"]
        found = load_object(out)["przelew_bankowy"] if out.is_file() and out.stat().st_size else {}
        complete += found == gold
        for field, expected in gold.items():
            current = counts.setdefault(field, Counter(tp=0, fp=0, fn=0))
            value = found.get(field)
            if value is not None and value == expected:
                current["tp"] += 1
            elif value != expected:
                current["fp"] += int(value is not None)
                current["fn"] += int(expected is not None)
    return {**{k: results[k] for k in ("micro_f1", "tp", "fp", "fn", "valid_run", "errors",
                                        "false_positive_documents")}, "valid_contract": contract["valid_contract"],
            "contract_errors": contract["errors"], "confusion_matrix": contract["confusion_matrix"],
            "zero_byte_negatives": negatives, "complete_transfers": complete, "fields": counts}


def compare(dataset, manifest, folder):
    entries = {Path(x["input"]).with_suffix(".json").as_posix(): x for x in load(manifest)["documents"]}
    calls = [json.loads(line) for line in (folder / "C/calls.jsonl").read_text().splitlines()]
    targets = {(q["output"], q["field"]) for q in load(folder / "queue/queue.json")["candidates"]}
    assert len(calls) == len(targets) and {(r["output"], r["field"]) for r in calls} == targets
    accepted = {k: {} for k in entries}
    field_results = []
    for r in calls:
        key, field = r["output"], r["field"]
        expected = load_object(dataset / entries[key]["reference"])["przelew_bankowy"][field]
        saved = load_object(folder / "C/output" / key)["przelew_bankowy"][field]
        if r["outcome"] == "accepted":
            accepted[key][field] = r["value"]
        field_results.append({"output": key, "field": field, "http": r.get("http"),
                              "outcome": r["outcome"], "correct": saved == expected,
                              "gold": str(expected), "saved": str(saved) if saved is not None else None})
    identical = 0
    for key in entries:
        base = (folder / "A/output" / key).read_bytes()
        candidate = (folder / "C/output" / key).read_bytes()
        if accepted[key]:
            reference = json.loads(base)
            for field, value in accepted[key].items():
                assert reference["przelew_bankowy"][field] is None
                reference["przelew_bankowy"][field] = value
            assert reference == json.loads(candidate), "Unexpected change in " + key
        else:
            assert candidate == base, "Unexpected bytes in " + key
        identical += candidate == base
    usage = {k: sum(r["usage"][k] for r in calls if r.get("usage"))
             for k in ("prompt_tokens", "completion_tokens")}
    return {"documents": len(entries), "unchanged_bytes": identical, "change_scope_valid": True,
            "A": metrics(dataset, manifest, folder / "A"), "C": metrics(dataset, manifest, folder / "C"),
            "targets": field_results, "api": load(folder / "C/summary.json"),
            "usage": usage, "calls_with_usage": sum(bool(r.get("usage")) for r in calls),
            "http_seconds": sum(r.get("transport_seconds", 0) for r in calls),
            "timing": load(folder / "timing.json")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.dataset, args.manifest, args.run),
                     ensure_ascii=False, indent=2, allow_nan=False))
