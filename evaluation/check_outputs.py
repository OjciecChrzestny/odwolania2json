"""Ocena drzewa, schematów i klas na podstawie zapisu sprzed pomiaru F1."""
import argparse
import json
from collections import Counter
from pathlib import Path

from odwolania2json.model import DEFAULT_CONFIG, load_classes, schema_errors


def read_json(path):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"powtórzony klucz {key}")
            obj[key] = value
        return obj

    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique)


def check_document(path, prediction, expected, classes):
    status = prediction["status"]
    name = prediction["class"]
    if status == "read_error":
        yield f"$: błąd odczytu PDF ({prediction.get('error', 'bez szczegółów')})"
        return
    if not path.is_file():
        yield "$: brak pliku wynikowego"
        return
    if expected == "negative" and path.stat().st_size:
        yield "$: dokument obcy wymaga pliku długości 0 bajtów"
    if name == "negative":
        if status != "negative" or path.stat().st_size:
            yield "$: rozpoznanie dokumentu obcego wymaga statusu negative i 0 bajtów"
        return
    if status != "ok" or name not in classes:
        yield f"$: nieprawidłowy status {status} lub rozpoznanie {name}"
        return
    try:
        value = read_json(path)
    except (OSError, ValueError) as exc:
        yield f"$: błędny JSON ({exc})"
        return
    config = classes[name]
    errors = list(schema_errors(value, config["schema"]))
    yield from errors
    if not errors and "reasons" in config:
        entry = value["OdwolanieKIO"]
        expected_description = config["reasons"]["descriptions"][str(entry["czynnosc_powod_id"])]
        if entry["czynnosc_opis"] != expected_description:
            yield "$.OdwolanieKIO.czynnosc_opis: opis niezgodny ze słownikiem dla podanego ID"


def check_outputs(output, manifest, diagnostics, classes):
    expected = {Path(row["input"]).with_suffix(".json").as_posix(): row["class"]
                for row in manifest["documents"]}
    errors = []
    seen = {}
    for item in diagnostics["documents"]:
        name = item["output"]
        if name in seen:
            errors.append(f"{name}: powtórzony rekord diagnostyki")
        seen[name] = item

    names = sorted(set(classes) | {"negative"})
    matrix = {name: dict.fromkeys([*names, "read_error", "missing", "unknown"], 0) for name in names}
    failures = set()
    for name, expected_class in sorted(expected.items()):
        item = seen.get(name)
        if item is None:
            matrix[expected_class]["missing"] += 1
            errors.append(f"{name}: brak zapisu diagnostyki")
            if not (output / name).is_file():
                errors.append(f"{name}: $: brak pliku wynikowego")
            failures.add(name)
            continue
        predicted = item["class"]
        row = matrix[expected_class]
        row[predicted if predicted in row else "unknown"] += 1
        problems = list(check_document(output / name, item, expected_class, classes))
        if problems:
            errors.extend(f"{name}: {error}" for error in problems)
            failures.add(name)
    extra = {p.relative_to(output).as_posix() for p in output.rglob("*.json")} - expected.keys()
    errors.extend(f"{name}: nadmiarowy plik wynikowy" for name in sorted(extra))
    errors.extend(f"{name}: nadmiarowy zapis diagnostyki" for name in sorted(seen.keys() - expected.keys()))
    return {"valid_contract": not errors, "errors": errors, "expected_documents": len(expected),
            "contract_documents": len(expected) - len(failures),
            "confusion_matrix": matrix}


def summarize_scores(score):
    totals = {}
    for doc in score["documents"]:
        counts = totals.setdefault(doc["class"], Counter())
        counts.update({key: doc[key] for key in ("tp", "fp", "fn")})
        counts["documents"] += 1
    for counts in totals.values():
        denominator = 2 * counts["tp"] + counts["fp"] + counts["fn"]
        counts["micro_f1"] = 2 * counts["tp"] / denominator if denominator else None
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--diagnostics", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--score", type=Path, help="opcjonalny raport niezmienionego miernika F1")
    args = parser.parse_args()
    try:
        result = check_outputs(args.output, read_json(args.manifest),
                               read_json(args.diagnostics), load_classes(args.config))
        if args.score:
            score = read_json(args.score)
            result["score"] = {key: value for key, value in score.items() if key != "documents"}
            result["by_class"] = summarize_scores(score)
    except (OSError, KeyError, ValueError) as exc:
        parser.exit(2, f"Błąd struktury przebiegu: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid_contract"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
