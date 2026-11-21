"""Niezależna ocena istniejącego raportu kontroli i drzewa wyników.

Uruchom: python3 -m evaluation.score_review DATASET OUTPUT --manifest MANIFEST --diagnostics RAPORT
Manifest miernika pól ma dodatkową listę pages dla każdego PDF-u. Strony we wzorcu są
numerowane od 1 i obejmują cały dokument. Pusta lista oznacza PDF bez ustalonych stron.
Zapis automatu pochodzi z --diagnostics CLI (report_version=1 w każdym dokumencie).
Wzorzec i zapis kandydata muszą pochodzić z osobnych procesów.
"""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from odwolania2json.model import DEFAULT_CONFIG, load_classes

from .check_outputs import check_document, read_json
from .score import score

PAGE_STATES = ("readable", "partial", "unreadable", "unassessed")
DECISIONS = ("auto_accepted", "review_required")
OUTCOMES = (*DECISIONS, "without_decision")


def is_relative_name(value):
    return (isinstance(value, str) and "\\" not in value
            and all(part not in {"", ".", ".."} for part in value.split("/")))


def reference_documents(manifest, classes):
    rows = manifest.get("documents")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Manifest wymaga niepustej listy documents.")
    by_output = {}
    for row in rows:
        source = row["input"]
        if not is_relative_name(source) or PurePosixPath(source).suffix.lower() != ".pdf":
            raise ValueError(f"Nieprawidłowa ścieżka input: {source!r}")
        output = PurePosixPath(source).with_suffix(".json").as_posix()
        if output in by_output:
            raise ValueError(f"Powtórzona ścieżka wynikowa w manifeście: {output}")
        negative = row["class"] == "negative"
        if not (negative or row["class"] in classes):
            raise ValueError(f"{source}: nieznana klasa wzorcowa.")
        if not is_relative_name(row["pdf"]) or (row["reference"] is None) != negative:
            raise ValueError(f"{source}: niespójne ścieżki PDF-u lub etykiety.")
        if not negative and not is_relative_name(row["reference"]):
            raise ValueError(f"{source}: nieprawidłowa ścieżka etykiety.")
        pages = row["pages"]
        if not isinstance(pages, list):
            raise ValueError(f"{source}: wzorzec wymaga listy pages.")
        for number, page in enumerate(pages, 1):
            if (not isinstance(page, dict) or type(page.get("page")) is not int
                    or page["page"] != number or page.get("status") not in PAGE_STATES):
                raise ValueError(f"{source}: nieprawidłowa etykieta strony {number}.")
        by_output[output] = row
    return by_output


def index_report(report, expected, errors):
    by_output = defaultdict(list)
    records = report.get("documents")
    if not isinstance(records, list):
        errors.append("Raport wymaga listy documents.")
        return by_output
    seen_inputs = set()
    for number, item in enumerate(records, 1):
        source = item.get("input") if isinstance(item, dict) else None
        if is_relative_name(source):
            if source in seen_inputs:
                errors.append(f"{source}: powtórzone wejście w diagnostyce.")
            seen_inputs.add(source)
        output = item.get("output") if isinstance(item, dict) else None
        if not is_relative_name(output):
            errors.append(f"Rekord raportu {number}: nieprawidłowa ścieżka output.")
        elif output not in expected:
            errors.append(f"{output}: nadmiarowy rekord diagnostyki.")
        else:
            by_output[output].append(item)
    return by_output


def compare_pages(expected, recorded, errors):
    by_page = defaultdict(list)
    if not isinstance(recorded, list):
        errors.append("brak listy stron w diagnostyce")
        recorded = []
    for page in recorded:
        number = page.get("page") if isinstance(page, dict) else None
        if type(number) is not int or not 1 <= number <= len(expected):
            errors.append(f"nieoczekiwana strona diagnostyki: {number!r}")
            continue
        by_page[number].append(page.get("status"))

    pages = []
    for gold in expected:
        number = gold["page"]
        statuses = by_page[number]
        observed = None
        if not statuses:
            errors.append(f"brak strony {number} w diagnostyce")
        elif len(statuses) > 1:
            errors.append(f"powtórzona strona {number} w diagnostyce")
        elif statuses[0] not in PAGE_STATES:
            errors.append(f"nieznany status strony {number} w diagnostyce")
        else:
            observed = statuses[0]
        pages.append({"page": number, "expected": gold["status"], "observed": observed})
    return pages


def verify_identity(record, row, target):
    errors = []
    if record.get("input") != row["input"] or record.get("pdf_sha256") != row["sha256"]:
        errors.append("ścieżka wejścia lub SHA-256 PDF-u różni się od manifestu")
    revision = record.get("extractor_revision")
    if not isinstance(revision, str) or not revision.strip():
        errors.append("brak rewizji ekstraktora")
    try:
        actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError:
        actual_hash = None
    if "output_sha256" not in record or record["output_sha256"] != actual_hash:
        errors.append("SHA-256 wyniku różni się od zapisanych bajtów lub plik nie istnieje")
    return errors


def evaluate_document(output, row, candidates, target, counts, classes):
    errors, defects = [], []
    profile = "unknown"
    decision = "without_decision"
    recorded_pages = []
    expected_status = "negative" if row["class"] == "negative" else "ok"
    # Validate the artifact against the independently labeled class, even with no report row.
    expected = {"class": row["class"], "status": expected_status}
    contract_errors = list(check_document(target, expected, row["class"], classes))
    errors.extend(contract_errors)
    defects.extend(contract_errors)
    if counts["fp"] or counts["fn"]:
        defects.append("wartości pól różnią się od wzorca")
    if len(candidates) != 1:
        errors.append("powtórzona ścieżka w diagnostyce" if candidates else "brak rekordu diagnostyki")
    else:
        record = candidates[0]
        if type(record.get("report_version")) is not int or record["report_version"] != 1:
            errors.append("nieobsługiwana wersja raportu diagnostyki")
        else:
            identity_errors = verify_identity(record, row, target)
            errors.extend(identity_errors)
            defects.extend(identity_errors)
            if record.get("class") != row["class"] or record.get("status") != expected_status:
                defects.append("klasa lub status odczytu różni się od wzorca")
            review = record.get("review")
            if not isinstance(review, dict) or review.get("status") not in DECISIONS:
                errors.append("brak prawidłowej decyzji automatu")
            else:
                decision = review["status"]
                applied = review.get("profile", record.get("class"))
                if isinstance(applied, str) and applied.strip():
                    profile = applied
            if record.get("input") == row["input"] and record.get("pdf_sha256") == row["sha256"]:
                recorded_pages = record.get("pages")
    pages = compare_pages(row["pages"], recorded_pages, errors)
    return {
        "input": row["input"], "output": output, "expected_class": row["class"],
        "profile": profile, "decision": decision, "correct": not defects,
        "defects": defects, "errors": errors, "fields": counts, "pages": pages,
    }


def fraction(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def summarize(documents):
    matrix = {label: dict.fromkeys(OUTCOMES, 0) for label in ("correct", "incorrect")}
    pages = Counter(expected=0, missing=0, unreadable=0, detected=0, false_positives=0)
    for doc in documents:
        label = "correct" if doc["correct"] else "incorrect"
        matrix[label][doc["decision"]] += 1
        for page in doc["pages"]:
            pages["expected"] += 1
            pages["missing"] += page["observed"] is None
            unreadable = page["expected"] == "unreadable"
            detected = page["observed"] == "unreadable"
            pages["unreadable"] += unreadable
            pages["detected"] += unreadable and detected
            pages["false_positives"] += detected and page["expected"] in ("readable", "partial")
    accepted = sum(row["auto_accepted"] for row in matrix.values())
    return {
        "decision_matrix": matrix,
        "coverage": fraction(accepted, len(documents)),
        "acceptance_accuracy": fraction(matrix["correct"]["auto_accepted"], accepted),
        "incorrect_review_rate": fraction(matrix["incorrect"]["review_required"],
                                          sum(matrix["incorrect"].values())),
        "pages": {**pages, "missed_unreadable": pages["unreadable"] - pages["detected"],
                  "unreadable_recall": fraction(pages["detected"], pages["unreadable"])},
    }


def score_review(dataset, output, manifest_path, diagnostics, config=DEFAULT_CONFIG):
    classes = load_classes(config)
    expected = reference_documents(read_json(manifest_path), classes)
    # Keep the existing field scoring, including its TP/FP/FN and validity semantics.
    field_score = score(dataset, output, manifest_path)
    by_output = {doc["output"]: {key: doc[key] for key in ("tp", "fp", "fn")}
                 for doc in field_score.pop("documents")}
    errors = []
    try:
        report = read_json(diagnostics)
        if not isinstance(report, dict):
            raise ValueError("oczekiwano obiektu JSON")
    except (OSError, ValueError) as exc:
        errors.append(f"Raport diagnostyki: {exc}")
        report = {"documents": []}
    records = index_report(report, expected, errors)
    revisions = {record["extractor_revision"] for group in records.values() for record in group
                 if isinstance(record.get("extractor_revision"), str) and record["extractor_revision"].strip()}
    if len(revisions) > 1:
        errors.append("W jednym przebiegu raport podaje różne rewizje ekstraktora.")
    documents = []
    profiles = defaultdict(list)
    for name, row in expected.items():
        doc = evaluate_document(name, row, records[name], output / name, by_output[name], classes)
        documents.append(doc)
        profiles[doc["profile"]].append(doc)
        errors.extend(f"{name}: {error}" for error in doc["errors"])
    return {
        "valid_run": not errors and field_score["valid_run"],
        "extractor_revisions": sorted(revisions),
        "errors": errors,
        "overall": summarize(documents),
        "by_profile": {profile: summarize(group) for profile, group in sorted(profiles.items())},
        "field_score": {
            **field_score,
            "micro_f1_denominator": 2 * field_score["tp"] + field_score["fp"] + field_score["fn"],
            "jury_compatibility_confirmed": False,
            "jury_compatibility_note": "Lokalny miernik evaluation/score.py. Brak porównania z miernikiem jury.",
        },
        "documents": documents,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("dataset", type=Path, help="katalog PDF-ów i zamrożonych etykiet")
    parser.add_argument("output", type=Path, help="drzewo wyników ekstraktora")
    parser.add_argument("--manifest", type=Path, required=True, help="manifest z niezależnymi etykietami stron")
    parser.add_argument("--diagnostics", type=Path, required=True, help="gotowy raport automatycznych decyzji")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="katalog schematów ocenianego przebiegu")
    args = parser.parse_args()
    try:
        result = score_review(args.dataset, args.output, args.manifest, args.diagnostics, args.config)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser.exit(2, f"Błąd wzorca lub konfiguracji: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid_run"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
