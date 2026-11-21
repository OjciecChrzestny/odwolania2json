"""Local strict field-level micro-F1 for a frozen UZP split."""
import argparse
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path


def load_object(path):
    value = json.loads(path.read_text(encoding="utf-8-sig"), parse_float=Decimal)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def fields(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from fields(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from fields(child, (*path, index))
    elif value is not None and value != "":
        kind = "bool" if isinstance(value, bool) else "number" if isinstance(value, (int, Decimal)) else "text"
        yield path, kind, value


def checked_file(root, name, digest, *, reference=False):
    path = root / name
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() == digest:
        return path
    if reference:
        # The original validation manifest hashes a CRLF checkout. New manifests use Git's LF.
        lf = data.replace(b"\r\n", b"\n")
        for representation in (lf, lf.replace(b"\n", b"\r\n")):
            if hashlib.sha256(representation).hexdigest() == digest:
                return path
    raise ValueError(f"Hash mismatch: {path}")


DEFAULT_MANIFEST = Path(__file__).with_name("validation-10.json")


def score(dataset, output, manifest_path=DEFAULT_MANIFEST):
    manifest = load_object(manifest_path)
    total = Counter(tp=0, fp=0, fn=0)
    docs, errors, expected_files = [], [], set()
    correct_ids = negative_hits = 0
    for entry in manifest["documents"]:
        checked_file(dataset, entry["pdf"], entry["sha256"])
        negative = entry["reference"] is None
        gold = {}
        if not negative:
            label = checked_file(dataset, entry["reference"], entry["reference_sha256"], reference=True)
            gold = load_object(label)
        relative = Path(entry["input"]).with_suffix(".json")
        expected_files.add(relative.as_posix())
        target = output / relative
        try:
            pred = {} if negative and not target.read_bytes().strip() else load_object(target)
        except (OSError, ValueError) as exc:
            errors.append(f"{relative}: {exc}")
            pred = {}
        expected, actual = set(fields(gold)), set(fields(pred))
        counts = dict(tp=len(expected & actual), fp=len(actual - expected), fn=len(expected - actual))
        total.update(counts)
        if negative:
            negative_hits += bool(pred)
        if entry["class"] == "odwolanie":
            section = pred.get("OdwolanieKIO")
            reason = section.get("czynnosc_powod_id") if isinstance(section, dict) else None
            correct_ids += type(reason) is int and reason == gold["OdwolanieKIO"]["czynnosc_powod_id"]
        docs.append({"output": relative.as_posix(), "class": entry["class"], **counts})
    extras = {p.relative_to(output).as_posix() for p in output.rglob("*.json")} - expected_files
    errors.extend(f"Unexpected output: {name}" for name in sorted(extras))
    denominator = 2 * total["tp"] + total["fp"] + total["fn"]
    return {**total, "micro_f1": 2 * total["tp"] / denominator if denominator else None,
            "valid_run": not errors, "correct_reason_ids": correct_ids, "false_positive_documents": negative_hits,
            "errors": errors, "documents": docs}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Root of the pinned UZP checkout")
    parser.add_argument("output", type=Path, help="Run output using neutral paths from the manifest")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                        help="Split manifest (default: validation-10.json)")
    args = parser.parse_args()
    result = score(args.dataset, args.output, args.manifest)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["valid_run"] else 1)
