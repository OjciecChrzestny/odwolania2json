"""Apply a bounded, one-shot Scaleway pilot to an already prepared A3 batch."""
import argparse
import json
import shutil
import time
from pathlib import Path

from experiments.abc.adapters import sha256
from .crops import LABELS
from .scaleway import FIELD_INSTRUCTIONS, PROVIDER, load_token, read_field


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def verify_queue(baseline, queue_root, expected_calls):
    queue = json.loads((queue_root / "queue.json").read_bytes())
    existing = {p.relative_to(baseline / "output").as_posix(): sha256(p.read_bytes())
                for p in (baseline / "output").rglob("*.json")}
    if existing != queue["base_outputs"]:
        raise ValueError("A3 outputs differ from the prepared batch")
    rows = queue["candidates"]
    if len(rows) > expected_calls:
        raise ValueError("Prepared batch exceeds the request budget")
    labels = set(LABELS.values())
    seen = set()
    for entry in rows:
        path, field = entry["output"], entry["field"]
        if path not in existing or field not in FIELD_INSTRUCTIONS or (path, field) in seen:
            raise ValueError("Invalid or repeated target field")
        seen.add((path, field))
        base = json.loads((baseline / "output" / path).read_bytes())
        if base["przelew_bankowy"][field] is not None:
            raise ValueError("Target field is already populated")
        pdf = (baseline / "input" / path).with_suffix(".pdf")
        if sha256(pdf.read_bytes()) != entry["pdf_sha256"]:
            raise ValueError("Source PDF changed")
        if not entry["rows"] and entry["panel_sha256"] is None:
            continue
        row_ids = [r["row"] for r in entry["rows"]]
        if not 1 <= len(row_ids) <= 12 or row_ids != list(range(1, len(row_ids) + 1)):
            raise ValueError("Invalid evidence rows")
        if any(set(r["labels"]) - labels for r in entry["rows"]):
            raise ValueError("Unrecognized OCR label")
        digest = entry["panel_sha256"]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid panel digest")
        panel = (queue_root / (digest + ".png")).read_bytes()
        if sha256(panel) != digest or not panel.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Panel evidence changed")
    return queue


def run(baseline, queue_root, destination, max_calls):
    started = time.monotonic()
    queue = verify_queue(baseline, queue_root, max_calls)
    token = load_token()
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    shutil.copytree(baseline / "output", destination / "output")
    diagnostics = json.loads((baseline / "diagnostics/last-run.json").read_bytes())
    by_output = {doc["output"]: doc for doc in diagnostics["documents"]}
    (destination / "diagnostics").mkdir()
    records = []
    halted = None
    with (destination / "calls.jsonl").open("x", encoding="utf-8") as journal:
        for entry in queue["candidates"]:
            name, field = entry["output"], entry["field"]
            record = {"output": name, "field": field, "panel_sha256": entry["panel_sha256"],
                      "attempted": False, "usage": None}
            if halted:
                record["outcome"] = "skipped_after_" + halted
            elif not entry["rows"]:
                record["outcome"] = "no_panel"
            else:
                png = (queue_root / (entry["panel_sha256"] + ".png")).read_bytes()
                record.update(read_field(token, field, png, entry["rows"]), attempted=True)
                if record["http"] in (401, 402, 403, 429):
                    halted = record["outcome"]
            journal.write(json.dumps(record, ensure_ascii=False) + "\n")
            journal.flush()
            if record["outcome"] == "accepted":
                path = destination / "output" / name
                result = json.loads(path.read_bytes())
                result["przelew_bankowy"][field] = record["value"]
                write_json(path, result)
                row = next(r for r in entry["rows"] if r["row"] == record["row"])
                by_output[name]["fields"]["przelew_bankowy." + field] = {
                    "page": row["page"], "rule": "scaleway_numeric_crop", "box": row["box"],
                    "render_scale": row["render_scale"], "panel_sha256": entry["panel_sha256"],
                    "row": row["row"], "model": PROVIDER.model,
                }
            records.append(record)
            print(f"{field} HTTP={record.get('http')} {record['outcome']}", flush=True)
    write_json(destination / "diagnostics/last-run.json", diagnostics)
    summary = {"model": PROVIDER.model, "seconds": time.monotonic() - started,
               "targets": len(records), "calls": sum(r["attempted"] for r in records),
               "accepted": sum(r["outcome"] == "accepted" for r in records),
               "abstained": sum(r["outcome"] == "abstained" for r in records),
               "valid_model_comparison": bool(records) and all(
                   r["outcome"] in ("accepted", "abstained", "no_panel") for r in records
               ) and any(r["attempted"] for r in records)}
    write_json(destination / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--max-calls", type=int, required=True)
    args = parser.parse_args()
    res = run(args.baseline, args.queue, args.destination, args.max_calls)
    raise SystemExit(0 if res["valid_model_comparison"] else 3)
