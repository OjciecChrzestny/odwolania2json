"""Kopiuje wskazane PDF-y do czystego drzewa wejściowego."""
import argparse
import shutil
from pathlib import Path

from score import checked_file, load_object


def prepare(dataset, manifest, destination, only=None):
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError(f"Katalog wejścia ma być pusty: {destination}")
    rows = load_object(manifest)["documents"]
    selected = [row for row in rows if only is None or row["input"] == only]
    if not selected:
        raise ValueError("Manifest nie zawiera wskazanego PDF-u")
    destination.mkdir(parents=True, exist_ok=True)
    for row in selected:
        name = Path(row["input"])
        if name.is_absolute() or ".." in name.parts or name.suffix.lower() != ".pdf":
            raise ValueError(f"Nieprawidłowa ścieżka wejścia: {name}")
        source = checked_file(dataset, row["pdf"], row["sha256"])
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as original, target.open("xb") as copy:
            shutil.copyfileobj(original, copy)
    return len(selected)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--only", help="jedna neutralna ścieżka do sprawdzenia")
    args = parser.parse_args()
    try:
        print(f"Skopiowano PDF-ów: {prepare(args.dataset, args.manifest, args.destination, args.only)}")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
