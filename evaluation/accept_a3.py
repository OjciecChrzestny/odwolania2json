"""Odbiór A3 na development-40, z dwiema zmianami ścieżki każdego dokumentu."""
import argparse
import hashlib
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from check_outputs import check_outputs
from odwolania2json.model import load_classes
from prepare_input import prepare
from score import score

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation/development-40.json"
WRONG_NAME = {"odwolanie": "przelew", "przelew": "pelnomocnictwo",
              "pelnomocnictwo": "odwolanie", "negative": "pelnomocnictwo"}


def read(path):
    return json.loads(path.read_bytes())


def save(path, record):
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def diagnostics(run):
    records = read(run / "diagnostics/extraction.json")["documents"]
    return {entry["output"]: {k: v for k, v in entry.items() if k != "output"} for entry in records}


def renamed_paths(entry):
    token = hashlib.sha256(("A3-name-test:" + entry["input"]).encode()).hexdigest()
    misleading = WRONG_NAME[entry["class"]]
    return (Path(token[:10]) / (token[10:32] + ".PDF"),
            Path(misleading) / token[32:42] / (misleading + ".pdf"))


def run(dataset, tools, baseline, work):
    work.mkdir(parents=True, exist_ok=False)
    product = work / "product"
    shutil.copytree(ROOT / "odwolania2json", product / "odwolania2json",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    regular, renamed = work / "neutral", work / "renamed"
    count = prepare(dataset, MANIFEST, regular / "input")
    rows = read(MANIFEST)["documents"]
    for row in rows:
        for name in renamed_paths(row):
            dest = renamed / "input" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with (regular / "input" / row["input"]).open("rb") as src, dest.open("xb") as dst:
                shutil.copyfileobj(src, dst)

    for folder in (regular, renamed):
        subprocess.run(["bash", str(ROOT / "evaluation/run_private_linux.sh"),
                        str(tools), str(product), str(folder)], check=True)
    metric = score(dataset, regular / "output", MANIFEST)
    contract = check_outputs(regular / "output", read(MANIFEST), read(regular / "diagnostics/extraction.json"),
                             load_classes(product / "odwolania2json/classes"))
    save(work / "score.json", metric)
    save(work / "contract.json", contract)
    normal, alternate = diagnostics(regular), diagnostics(renamed)
    expected_alternate = {p.with_suffix(".json").as_posix() for row in rows for p in renamed_paths(row)}
    actual_files = {p.relative_to(renamed / "output").as_posix() for p in (renamed / "output").rglob("*.json")}
    assert set(alternate) == actual_files == expected_alternate and len(alternate) == 2 * count

    identical = 0
    renamed_ok = Counter()
    classes = Counter()
    for row in rows:
        name = Path(row["input"]).with_suffix(".json").as_posix()
        data = (regular / "output" / name).read_bytes()
        identical += data == (baseline / "output" / name).read_bytes()
        if normal[name]["class"] == row["class"]:
            classes[row["class"]] += 1
        for mode, other in zip(("losowe", "mylące"), renamed_paths(row)):
            other = other.with_suffix(".json").as_posix()
            if data != (renamed / "output" / other).read_bytes() or normal[name] != alternate[other]:
                raise ValueError(f"Wynik lub diagnostyka zależą od ścieżki dla {name} ({mode})")
            renamed_ok[mode] += 1

    old = read(baseline / "score.json")
    before = {doc["output"]: doc for doc in old["documents"]}
    regressions = [doc["output"] for doc in metric["documents"] if any((
        doc["tp"] < before[doc["output"]]["tp"], doc["fp"] > before[doc["output"]]["fp"],
        doc["fn"] > before[doc["output"]]["fn"]))]
    report = {"development_pdfs": count, "correct_classes": classes, "identical_to_a2": identical,
              "per_document_regressions": regressions, "identical_output_and_diagnostics_after_rename": renamed_ok,
              "valid_contract": contract["valid_contract"],
              **{k: metric[k] for k in ("valid_run", "micro_f1", "tp", "fp", "fn", "correct_reason_ids",
                                          "false_positive_documents")}}
    save(work / "summary.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if regressions or not metric["valid_run"] or not contract["valid_contract"] or sum(classes.values()) != count:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("dataset", "tools", "baseline", "work"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    run(args.dataset.resolve(), args.tools.resolve(), args.baseline.resolve(), args.work.resolve())
