"""Project the shared amount responses onto A3 without another provider request."""
import argparse
import json
from pathlib import Path
import shutil

from .run import write_json


def project(baseline, combined, destination):
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    shutil.copytree(baseline / "output", destination / "output")
    (destination / "diagnostics").mkdir()
    diagnostics = json.loads((baseline / "diagnostics/last-run.json").read_bytes())
    changed = json.loads((combined / "diagnostics/last-run.json").read_bytes())
    docs = {d["output"]: d for d in diagnostics["documents"]}
    provenance = {d["output"]: d for d in changed["documents"]}
    for line in (combined / "calls.jsonl").read_text().splitlines():
        rec = json.loads(line)
        if rec["field"] != "kwota" or rec["outcome"] != "accepted":
            continue
        name = rec["output"]
        path = destination / "output" / name
        original = json.loads(path.read_bytes())
        combined_value = json.loads((combined / "output" / name).read_bytes())["przelew_bankowy"]["kwota"]
        if original["przelew_bankowy"]["kwota"] is not None or rec["value"] != combined_value:
            raise ValueError("Amount replay differs from persisted prediction")
        original["przelew_bankowy"]["kwota"] = combined_value
        write_json(path, original)
        docs[name]["fields"]["przelew_bankowy.kwota"] = provenance[name]["fields"]["przelew_bankowy.kwota"]
    write_json(destination / "diagnostics/last-run.json", diagnostics)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline", "combined", "destination"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    project(args.baseline, args.combined, args.destination)
