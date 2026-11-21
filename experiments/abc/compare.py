"""Porównanie istniejących drzew A/B/C. Działa lokalnie, bez transportu."""
import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from evaluation.check_outputs import check_outputs, read_json, summarize_scores
from evaluation.score import checked_file, score
from odwolania2json.__main__ import json_bytes
from odwolania2json.model import load_classes

from .adapters import IDS, PROVIDERS, REASON_FIELD, sha256
from .run import checked_descriptions


def index(report, expected):
    rows = {row["output"]: row for row in report["documents"]}
    if len(rows) != len(report["documents"]) or rows.keys() != expected.keys():
        raise ValueError("Diagnostyka nie odpowiada ścieżkom manifestu")
    return rows


def a_batch_seconds(path):
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if "Elapsed (wall clock) time" in line:
            seconds = 0.0
            for part in line.rsplit("): ", 1)[1].split(":"):
                seconds = seconds * 60 + float(part)
            return seconds
    return None


def tree_summary(result, root, manifest, diagnostics, classes):
    output = root / "output"
    contract = check_outputs(output, manifest, diagnostics, classes)
    counts = Counter(row["class"] for row in manifest["documents"])
    return {
        **{key: result[key] for key in ("tp", "fp", "fn", "micro_f1", "valid_run",
                                        "correct_reason_ids", "false_positive_documents")},
        "appeals": counts["odwolanie"],
        "negatives": counts["negative"],
        "scorer_error_count": len(result["errors"]),
        "valid_contract": contract["valid_contract"],
        "contract_documents": contract["contract_documents"],
        "confusion_matrix": contract["confusion_matrix"],
        "by_class": summarize_scores(result),
    }


def optional_bytes(path):
    return path.read_bytes() if path.is_file() else None


def verify_document(name, a, variant, baseline, candidate, descriptions):
    if (candidate["class"], candidate["status"]) != (baseline["class"], baseline["status"]):
        raise ValueError(f"{name}: B/C zmieniło klasyfikację albo status A")
    if candidate.get("ocr_pages") != baseline.get("ocr_pages"):
        raise ValueError(f"{name}: A i B/C użyły innych stron OCR")
    if candidate["status"] == "read_error" and a is None and variant is None:
        return
    if a is None or variant is None or candidate.get("a_sha256") != sha256(a):
        raise ValueError(f"{name}: wynik A z przebiegu B/C nie odpowiada zapisanemu A")
    decision = candidate["experiment"]
    if decision["outcome"] != "success":
        if variant != a:
            raise ValueError(f"{name}: wynik bez zaakceptowanej odpowiedzi różni się od A")
        return
    original, revised = json.loads(a), json.loads(variant)
    section = revised["OdwolanieKIO"]
    reason_id = section[REASON_FIELD]
    if (candidate["class"] != "odwolanie" or type(reason_id) is not int or reason_id not in IDS
            or section["czynnosc_opis"] != descriptions[str(reason_id)]):
        raise ValueError(f"{name}: nieprawidłowa zmiana ID lub opisu")
    original["OdwolanieKIO"].update({key: section[key] for key in (REASON_FIELD, "czynnosc_opis")})
    if json_bytes(original) != variant:
        raise ValueError(f"{name}: niedozwolona zmiana poza ID i opisem")


def model_summary(rows, mode, provider):
    experiments = [row.get("experiment", {}) for row in rows.values()]
    attempts = [entry for entry in experiments if entry.get("attempted")]
    usage = [entry["usage"] for entry in attempts if entry.get("usage") is not None]
    prompt = sum(item["prompt_tokens"] for item in usage)
    completion = sum(item["completion_tokens"] for item in usage)
    cost = None
    if mode == "live" and usage:
        cost = str((prompt * Decimal(provider.input_eur_per_million)
                    + completion * Decimal(provider.output_eur_per_million)) / 1000000)
    return {
        "attempts": len(attempts),
        "fallbacks_to_a": sum(item.get("outcome") == "fallback" for item in experiments),
        "fallback_causes": dict(Counter(item["cause"] for item in experiments
                                        if item.get("outcome") == "fallback")),
        "prompt_tokens_reported": prompt,
        "completion_tokens_reported": completion,
        "responses_with_usage": len(usage),
        "attempts_without_usage": len(attempts) - len(usage),
        "estimated_cost_eur_for_reported_tokens": cost,
        "documents": {name: {"seconds": row["document_seconds"],
                             "transport_seconds": row.get("experiment", {}).get("transport_seconds")}
                      for name, row in rows.items()},
    }


def compare(dataset, manifest_path, roots):
    if len({root.resolve() for root in roots.values()}) != 3:
        raise ValueError("Przebiegi A, B i C wymagają trzech odrębnych katalogów")
    manifest = read_json(manifest_path)
    documents = manifest["documents"]
    expected = {}
    for row in documents:
        source = Path(row["input"])
        if source.is_absolute() or ".." in source.parts or source.suffix.lower() != ".pdf":
            raise ValueError("Manifest zawiera niedozwoloną ścieżkę neutralną")
        expected[source.with_suffix(".json").as_posix()] = row
        checked_file(roots["A"] / "input", row["input"], row["sha256"])
    if len(expected) != len(documents):
        raise ValueError("Manifest zawiera powtórzone ścieżki wyjścia")
    classes = load_classes()
    descriptions = checked_descriptions(classes)
    reports = {label: read_json(root / "diagnostics" /
                                ("extraction.json" if label == "A" else "experiment.json"))
               for label, root in roots.items()}
    modes = {reports[label]["mode"] for label in PROVIDERS}
    if len(modes) != 1 or modes - {"test_technical", "live"}:
        raise ValueError("B/C muszą działać w tym samym trybie")
    mode, = modes
    indexed = {label: index(report, expected) for label, report in reports.items()}
    for label, provider in PROVIDERS.items():
        if (reports[label]["variant"], reports[label]["model"]) != (label, provider.model):
            raise ValueError(f"Nieprawidłowa konfiguracja przebiegu {label}")

    matched_requests = 0
    for name, manifest_row in expected.items():
        a = optional_bytes(roots["A"] / "output" / name)
        b, c = (indexed[label][name] for label in PROVIDERS)
        for label, row in zip(PROVIDERS, (b, c), strict=True):
            if row["input_sha256"] != manifest_row["sha256"]:
                raise ValueError(f"{name}: bajty PDF przebiegu {label} różnią się od manifestu")
            verify_document(name, a, optional_bytes(roots[label] / "output" / name),
                            indexed["A"][name], row, descriptions)
        if (b.get("first_allegation") != c.get("first_allegation")
                or b.get("allegation_structure") != c.get("allegation_structure")
                or b.get("decision_source") != c.get("decision_source")
                or b.get("experiment", {}).get("request_sha256") !=
                c.get("experiment", {}).get("request_sha256")):
            raise ValueError(f"{name}: B/C przekazały różne wejście modelu")
        matched_requests += "request_sha256" in b.get("experiment", {})

    results = {label: score(dataset, root / "output", manifest_path) for label, root in roots.items()}
    summaries = {label: tree_summary(results[label], root, manifest, reports[label], classes)
                 for label, root in roots.items()}
    baseline_f1 = summaries["A"]["micro_f1"]
    summaries["A"]["batch_seconds"] = a_batch_seconds(roots["A"] / "time.txt")
    summaries["A"]["document_times_available"] = False
    for label, provider in PROVIDERS.items():
        summary = summaries[label]
        f1 = summary["micro_f1"]
        summary["delta_micro_f1_pp"] = (f1 - baseline_f1) * 100 if None not in (baseline_f1, f1) else None
        summary["batch_seconds"] = reports[label]["batch_seconds"]
        summary["field_count_changes"] = {
            candidate["output"]: {key: candidate[key] - base[key] for key in ("tp", "fp", "fn")}
            for base, candidate in zip(results["A"]["documents"], results[label]["documents"], strict=True)
            if base != candidate
        }
        summary.update(model_summary(indexed[label], mode, provider))
    return {"mode": mode, "pdfs": len(expected), "shared_request_hashes": matched_requests,
            "manifest_sha256": sha256(manifest_path.read_bytes()), "variants": summaries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    for label in ("a", "b", "c"):
        parser.add_argument(f"--{label}", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = compare(args.dataset, args.manifest, {"A": args.a, "B": args.b, "C": args.c})
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"Błąd porównania: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
