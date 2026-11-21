"""Re-score the sealed transfer benchmark and shared Scaleway responses without network calls."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from .compare import compare, load, metrics


def subset_metrics(dataset, manifest, run, variant):
    docs = load(manifest)["documents"]
    names = {Path(row["input"]).with_suffix(".json").as_posix() for row in docs}
    source = run / variant
    with tempfile.TemporaryDirectory() as tmp:
        view = Path(tmp)
        (view / "output").mkdir()
        for name in sorted(names):
            src = source / "output" / name
            if src.is_file():
                dest = view / "output" / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
        diag = load(source / "diagnostics/last-run.json")
        diag["documents"] = [row for row in diag["documents"] if row["output"] in names]
        (view / "diagnostics").mkdir()
        (view / "diagnostics/last-run.json").write_text(json.dumps(diag))
        return metrics(dataset, manifest, view)


def report(dataset, run):
    manifest = dataset / "manifests/all.json"
    full = compare(dataset, manifest, run)
    full["amount"] = metrics(dataset, manifest, run / "amount")
    variants = ("A", "amount", "C")
    full["cohorts"] = {name: {variant: subset_metrics(dataset, dataset / "manifests" / (name + ".json"),
                                                      run, variant) for variant in variants}
                       for name in ("public", "synthetic")}
    cases = []
    for doc in load(manifest)["documents"]:
        name = Path(doc["input"]).with_suffix(".json")
        base = (run / "A/output" / name).read_bytes()
        amount = (run / "amount/output" / name).read_bytes()
        combined = (run / "C/output" / name).read_bytes()
        if amount != base or combined != base:
            a = json.loads(base)
            c = json.loads(combined)["przelew_bankowy"]
            if a["przelew_bankowy"]["kwota"] is None:
                a["przelew_bankowy"]["kwota"] = c["kwota"]
            if json.loads(amount) != a:
                raise ValueError(f"{name}: amount-only projection changed another field")
        gold = load(dataset / doc["reference"])["przelew_bankowy"] if doc["reference"] else {}
        item = {"input": doc["input"], "class": doc["class"]}
        for variant in variants:
            value = (run / variant / "output" / name).read_bytes()
            guessed = json.loads(value).get("przelew_bankowy", {}) if value else {}
            item[variant] = {field: ("missing" if guessed.get(field) is None else
                                     "unexpected" if expected is None else "wrong")
                             for field, expected in gold.items() if guessed.get(field) != expected}
            if not gold:
                item[variant] = {"negative_zero_bytes": value == b""}
        cases.append(item)
    full["by_document"] = cases
    return full


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(report(args.dataset, args.run), indent=2, ensure_ascii=False))
