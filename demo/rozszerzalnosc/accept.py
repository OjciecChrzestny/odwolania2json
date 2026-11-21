"""Odbiór publicznego CLI na syntetykach i dozwolonym podzbiorze development."""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from pypdf import PdfReader

from pokaz import HERE, ROOT, prepare

BASE = "0dd1ed2f37f109dc7750c1309402bfb3a2b557e9"
DEVELOPMENT = ROOT / "evaluation/development-40.json"


def equal(actual, expected, label):
    if actual != expected:
        raise ValueError(f"{label}: otrzymano {actual!r}, oczekiwano {expected!r}")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def development_input(dataset, destination):
    manifest = json.loads(DEVELOPMENT.read_bytes())
    revision = subprocess.check_output(
        ["git", "-C", dataset, "rev-parse", "HEAD"], text=True,
    ).strip()
    equal(revision, manifest["revision"], "Rewizja danych UZP")
    classes = {}
    for row in manifest["documents"]:
        relative = Path(row["input"])
        if relative.parts[0] != "case_10" and row["class"] != "negative":
            continue
        source = dataset / row["pdf"]
        equal(sha(source), row["sha256"], f"SHA-256 {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        classes[relative.with_suffix(".json").as_posix()] = row["class"]
    equal(sorted(value for name, value in classes.items() if name.startswith("case_10/")),
          ["negative", "odwolanie", "pelnomocnictwo", "przelew"], "Klasy case_10")
    equal(list(classes.values()).count("negative"), 8, "Liczba negatywów development")
    return classes


def project_code(work):
    baseline, candidate = work / "kod-a", work / "kod-demo"
    baseline.mkdir()
    archive = subprocess.check_output(["git", "archive", BASE, "odwolania2json"], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as code:
        code.extractall(baseline, filter="data")
    shutil.copytree(ROOT / "odwolania2json", candidate / "odwolania2json",
                    ignore=shutil.ignore_patterns("__pycache__"))
    return baseline, candidate


def run_cli(args, code, input_dir, name, config=None, ocr=False):
    output = args.work / name
    diagnostic_dir = args.work / "diagnostics"
    diagnostic_dir.mkdir(exist_ok=True)
    diagnostics = diagnostic_dir / f"{name}.json"
    command = [sys.executable, "-m", "odwolania2json", "--input", input_dir,
               "--output", output, "--diagnostics", diagnostics]
    reads = [code, input_dir]
    if config:
        command += ["--config", config]
        reads.append(config)
    if ocr:
        command += ["--ocr-data", args.ocr_data]
        reads.append(args.ocr_data)
    if args.restrict_linux:
        output.mkdir()
        journal = output.with_name(f".{output.name}.odwolania2json")
        journal.mkdir()
        prefix = [args.restrict_linux]
        for path in ["/usr", "/etc/ld.so.cache", "/dev/null", "/dev/urandom",
                     sys.base_prefix, sys.prefix, *reads]:
            prefix += ["-r", path]
        for path in [output, journal, diagnostic_dir]:
            prefix += ["-w", path]
        command = prefix + ["--"] + command
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
           "OMP_THREAD_LIMIT": "1"}
    for name in ("PYTHONPATH", "UZP_DATA"):
        env.pop(name, None)
    subprocess.run(command, cwd=code, env=env, check=True)
    rows = json.loads(diagnostics.read_bytes())["documents"]
    return output, {row["output"]: row for row in rows}


def results(output, records, classes):
    equal(set(records), set(classes), f"Ścieżki diagnostyki {output.name}")
    files = {path.relative_to(output).as_posix() for path in output.rglob("*.json") if path.is_file()}
    equal(files, set(classes), f"Ścieżki JSON {output.name}")
    for name, label in classes.items():
        equal(records[name]["class"], label, f"Klasa {name} ({output.name})")
        negative = label == "negative"
        equal(records[name]["status"], "negative" if negative else "ok", f"Status {name}")
        equal((output / name).stat().st_size == 0, negative, f"Pusty JSON {name} ({output.name})")
    return {name: sha(output / name) for name in sorted(files)}


def synthetic(args, baseline, candidate, config):
    expected = json.loads((HERE / "expected.json").read_bytes())
    input_dir = args.work / "input"
    negatives = dict.fromkeys(expected, "negative")
    for code, name in [(baseline, "syntetyki-a"), (candidate, "syntetyki-domyslne")]:
        results(*run_cli(args, code, input_dir, name), negatives)
        print(f"{name} | {len(negatives)}/{len(negatives)} wyników po 0 B")
    if args.before:
        return
    classes = {name: "zawiadomienie" if spec else "negative" for name, spec in expected.items()}
    output, records = run_cli(args, candidate, input_dir, "syntetyki-demo", config)
    results(output, records, classes)
    for name, spec in expected.items():
        if spec is None:
            print(f"{name} | negatyw w profilu demo | 0 B")
            continue
        value = json.loads((output / name).read_bytes())
        equal(value, spec["result"], f"Pola {name}")
        equal(records[name]["signals"], spec["signals"], f"Sygnały {name}")
        equal(records[name]["fields"], spec["fields"], f"Źródła {name}")
        pdf = PdfReader(input_dir / Path(name).with_suffix(".pdf"))
        print(f"{name} | {json.dumps(value, ensure_ascii=False)}")
        for field, observed in records[name]["fields"].items():
            page = observed["page"]
            line = spec["source_lines"][field]
            equal(line in pdf.pages[page - 1].extract_text().splitlines(), True, f"Wiersz {name} s. {page}")
            print(f"  {field} | s. {page} | {observed['rule']} | {line}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True, help="nowy katalog przebiegu")
    parser.add_argument("--dataset", type=Path, required=True, help="przypięta kopia UZP")
    parser.add_argument("--ocr-data", type=Path, required=True, help="katalog pol.traineddata")
    parser.add_argument("--restrict-linux", type=Path, help="opcjonalny izolator Landlock z evaluation")
    parser.add_argument("--before", action="store_true", help="odbiór przed dodaniem pliku konfiguracji")
    args = parser.parse_args()
    for name in ("work", "dataset", "ocr_data", "restrict_linux"):
        path = getattr(args, name)
        if path:
            setattr(args, name, path.resolve())
    prepare(args.work)
    baseline, candidate = project_code(args.work)
    config = args.work / "klasy"
    if not args.before:
        shutil.copyfile(HERE / "zawiadomienie.json", config / "zawiadomienie.json")
    synthetic(args, baseline, candidate, config)
    input_dir = args.work / "development-pdf"
    classes = development_input(args.dataset, input_dir)
    reference = results(*run_cli(args, baseline, input_dir, "development-a", ocr=True), classes)
    compared = results(*run_cli(args, candidate, input_dir, "development-demo", config, ocr=True), classes)
    equal(compared, reference, "Ścieżki i SHA-256 JSON-ów development")
    for name, digest in compared.items():
        print(f"{name} | {classes[name]} | {digest}")
    print(f"Regresja: {len(compared)}/{len(classes)} zgodnych ścieżek i SHA-256, 8/8 negatywów po 0 B.")
    print(f"Dowody przebiegu: {args.work}")


if __name__ == "__main__":
    main()
