"""Prepare an identical, reference-free queue for both external APIs."""
import argparse
import json
import time
from pathlib import Path

from experiments.abc.adapters import sha256
from .crops import numeric_panel


def prepare(baseline, queue, tessdata):
    queue.mkdir(mode=0o700, parents=True, exist_ok=False)
    prepared = []
    hashes = {}
    started = time.monotonic()
    for path in sorted((baseline / "output").rglob("*.json")):
        name = path.relative_to(baseline / "output")
        raw = path.read_bytes()
        hashes[name.as_posix()] = sha256(raw)
        if not raw:
            continue
        transfer = json.loads(raw).get("przelew_bankowy")
        if transfer is None:
            continue
        for field in ("kwota", "data_operacji"):
            if transfer[field] is not None:
                continue
            pdf = baseline / "input" / name.with_suffix(".pdf")
            png, rows = numeric_panel(pdf, field, tessdata)
            digest = sha256(png) if png else None
            if png:
                (queue / (digest + ".png")).write_bytes(png)
            prepared.append({"output": name.as_posix(), "pdf_sha256": sha256(pdf.read_bytes()),
                             "field": field, "panel_sha256": digest, "rows": rows})
    batch = {"base_outputs": hashes, "candidates": prepared, "prepare_seconds": time.monotonic() - started}
    (queue / "queue.json").write_text(json.dumps(batch, indent=2) + "\n", encoding="utf-8")
    print(f"PDF results: {len(hashes)}, missing fields: {len(prepared)}, panels: {sum(bool(r['rows']) for r in prepared)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--tessdata", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.baseline, args.queue, args.tessdata)
