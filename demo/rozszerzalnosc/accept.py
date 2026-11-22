"""Odbiór zmiany profilu przez publiczne CLI na syntetykach i podzbiorze DEV."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from pokaz import HERE, ROOT, prepare, write_new_notice

DEVELOPMENT = ROOT / "evaluation/development-40.json"
DEFAULT_CONFIG = ROOT / "odwolania2json/classes"
EXTRA_CLASS = HERE / "zawiadomienie.json"
CONTEST_CLASSES = ["negative", "odwolanie", "pelnomocnictwo", "przelew"]


def equal(actual, expected, label):
    if actual != expected:
        raise ValueError(f"{label}: otrzymano {actual!r}, oczekiwano {expected!r}")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def development_input(dataset, destination, subset_manifest):
    manifest = json.loads(DEVELOPMENT.read_bytes())
    revision = subprocess.check_output(
        ["git", "-C", dataset, "rev-parse", "HEAD"], text=True,
    ).strip()
    equal(revision, manifest["revision"], "Rewizja danych UZP")
    classes, selected = {}, []
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
        selected.append(row)
    equal(sorted(label for name, label in classes.items() if name.startswith("case_10/")),
          CONTEST_CLASSES, "Klasy case_10")
    equal(list(classes.values()).count("negative"), 8, "Negatywy DEV")
    subset_manifest.write_text(
        json.dumps({**manifest, "documents": selected}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return classes


def run_cli(args, code, input_dir, name, config, ocr_data=None):
    output = args.work / name
    diagnostics = args.work / "diagnostics" / f"{name}.json"
    diagnostics.parent.mkdir(exist_ok=True)
    command = [sys.executable, "-m", "odwolania2json", "--input", input_dir,
               "--output", output, "--diagnostics", diagnostics]
    reads = [code, input_dir]
    if config is not None:
        command += ["--config", config]
        reads.append(config)
    if ocr_data is not None:
        command += ["--ocr-data", ocr_data]
        reads.append(ocr_data)
    if args.restrict_linux:
        output.mkdir()
        journal = output.with_name(f".{output.name}.odwolania2json")
        journal.mkdir()
        prefix = [args.restrict_linux]
        for path in ["/usr", "/etc/ld.so.cache", "/dev/null", "/dev/urandom",
                     sys.base_prefix, sys.prefix, *reads]:
            prefix += ["-r", path]
        for path in [output, journal, diagnostics.parent]:
            prefix += ["-w", path]
        command = prefix + ["--"] + command
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
           "OMP_THREAD_LIMIT": "1"}
    for variable in ("PYTHONPATH", "UZP_DATA"):
        env.pop(variable, None)
    subprocess.run(command, cwd=code, env=env, check=True)
    rows = json.loads(diagnostics.read_bytes())["documents"]
    records = {row["output"]: row for row in rows}
    equal(len(records), len(rows), f"Unikatowe rekordy diagnostyki {name}")
    return output, records


def results(output, records, classes):
    equal(set(records), set(classes), f"Ścieżki diagnostyki {output.name}")
    files = {path.relative_to(output).as_posix() for path in output.rglob("*.json") if path.is_file()}
    equal(files, set(classes), f"Ścieżki JSON {output.name}")
    for name, label in classes.items():
        equal(records[name]["class"], label, f"Klasa {name} ({output.name})")
        negative = label == "negative"
        equal(records[name]["status"], "negative" if negative else "ok", f"Status {name} ({output.name})")
        equal((output / name).stat().st_size == 0, negative, f"Pusty JSON {name} ({output.name})")
    return {name: sha(output / name) for name in sorted(files)}


def synthetic(input_dir, output, records, expected, extended):
    classes = {name: "zawiadomienie" if extended and spec else "negative"
               for name, spec in expected.items()}
    digests = results(output, records, classes)
    negatives = list(classes.values()).count("negative")
    print(f"{output.name} | {negatives}/{len(classes)} wyników 0 B", flush=True)
    if not extended:
        return digests

    from pypdf import PdfReader

    verified_fields = 0
    for name, spec in expected.items():
        if spec is None:
            print(f"{name} | negatyw w profilu demo | 0 B")
            continue
        value = json.loads((output / name).read_bytes())
        equal(value, spec["result"], f"Pola {name}")
        equal(records[name]["signals"], spec["signals"], f"Sygnały {name}")
        equal(set(records[name]["fields"]), set(spec["fields"]), f"Źródła pól {name}")
        pdf = PdfReader(input_dir / Path(name).with_suffix(".pdf"))
        print(f"{name} | {json.dumps(value, ensure_ascii=False)}")
        for field, observed in records[name]["fields"].items():
            page = observed["page"]
            reference = spec["fields"][field]
            equal((page, observed["rule"]), (reference["page"], reference["rule"]), f"Podstawa {name} {field}")
            equal(observed["source"], "text", f"Źródło tekstowe {name} {field}")
            equal(observed["precision"] in {"page", "snippet"}, True, f"Dokładność {name} {field}")
            line = spec["source_lines"][field]
            if observed["precision"] == "snippet":
                snippet = observed["snippet"]
                equal(bool(snippet.strip()) and snippet in line, True, f"Fragment {name} {field}")
            equal(line in pdf.pages[page - 1].extract_text().splitlines(), True, f"Wiersz {name} s. {page}")
            verified_fields += 1
            print(f"  {field} | s. {page} | {observed['rule']} | {line}")
    print(f"Profil demo | {len(classes) - negatives}/{len(classes)} zawiadomienia, "
          f"{verified_fields} zweryfikowanych pól ze źródłem.", flush=True)
    return digests


def profile_files(config):
    return {path.name: sha(path) for path in sorted(config.glob("*.json"))}


def profiles(work):
    config = work / "klasy"
    names = sorted(json.loads(path.read_bytes())["class"] for path in DEFAULT_CONFIG.glob("*.json"))
    equal(names, CONTEST_CLASSES[1:], "Klasy profilu konkursowego")
    stock = profile_files(DEFAULT_CONFIG)
    equal(profile_files(config), stock, "Kopia profilu konkursowego")
    yield "konkurs", None

    extra = config / EXTRA_CLASS.name
    if extra.exists():
        raise ValueError(f"Plik już istnieje w profilu konkursowym: {extra}")
    shutil.copyfile(EXTRA_CLASS, extra)
    equal(profile_files(config), {**stock, extra.name: sha(EXTRA_CLASS)}, "Jeden nowy plik profilu")
    diff = subprocess.run(
        ["git", "diff", "--no-index", "--", DEFAULT_CONFIG, config],
        capture_output=True,
    )
    equal(diff.returncode, 1, f"Różnica profili ({diff.stderr.decode(errors='replace')})")
    (work / "roznica-konfiguracji.diff").write_bytes(diff.stdout)
    print(f"Profil demo | +{extra.name} | {sha(extra)}", flush=True)
    yield "demo", config

    extra.unlink()
    equal(profile_files(config), stock, "Przywrócona kopia profilu konkursowego")
    yield "przywrocony", config


def score_development(args, output, subset_manifest):
    path = args.work / "development-score.json"
    with path.open("wb") as stream:
        subprocess.run(
            [sys.executable, ROOT / "evaluation/score.py", args.dataset, output, "--manifest", subset_manifest],
            stdout=stream, check=True,
        )
    score = json.loads(path.read_bytes())
    equal((score["fp"], score["fn"]), (0, 0), f"Pola względem etykiet DEV ({path})")
    for row in score["documents"]:
        if row["class"] != "negative":
            print(f"{row['class']} | {row['tp']}/{row['tp'] + row['fn']} pól względem etykiet")
    print(f"Etykiety DEV | TP={score['tp']}, FP={score['fp']}, FN={score['fn']}, "
          f"mikro-F1={score['micro_f1']:.2%}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True, help="nowy katalog przebiegu")
    parser.add_argument("--dataset", type=Path, help="przypięta kopia danych DEV do pełnego odbioru")
    parser.add_argument("--ocr-data", type=Path, help="opcjonalny katalog pol.traineddata dla DEV")
    parser.add_argument("--restrict-linux", type=Path, help="opcjonalny izolator Landlock z evaluation")
    args = parser.parse_args()
    if args.ocr_data and not args.dataset:
        parser.error("--ocr-data wymaga --dataset")
    for name in ("work", "dataset", "ocr_data", "restrict_linux"):
        path = getattr(args, name)
        if path:
            setattr(args, name, path.resolve())

    prepare(args.work)
    input_dir = args.work / "input"
    fresh = input_dir / "wejscie-04.pdf"
    write_new_notice(fresh)
    print(f"Nowy PDF | {fresh.name} | SHA-256 {sha(fresh)}", flush=True)
    expected = json.loads((HERE / "expected.json").read_bytes())

    code = args.work / "kod"
    shutil.copytree(ROOT / "odwolania2json", code / "odwolania2json",
                    ignore=shutil.ignore_patterns("__pycache__"))
    dev_input = args.work / "development-pdf"
    subset_manifest = args.work / "development-manifest.json"
    if args.dataset:
        dev_classes = development_input(args.dataset, dev_input, subset_manifest)

    synthetic_digests, development_digests = {}, {}
    for phase, config in profiles(args.work):
        output, records = run_cli(args, code, input_dir, f"syntetyki-{phase}", config)
        synthetic_digests[phase] = synthetic(input_dir, output, records, expected, phase == "demo")
        if args.dataset:
            output, records = run_cli(args, code, dev_input, f"development-{phase}", config, args.ocr_data)
            development_digests[phase] = results(output, records, dev_classes)

    equal(synthetic_digests["przywrocony"], synthetic_digests["konkurs"], "Powrót syntetyków do profilu konkursowego")
    if args.dataset:
        reference = development_digests["konkurs"]
        for phase in ("demo", "przywrocony"):
            equal(development_digests[phase], reference, f"Ścieżki i SHA-256 DEV ({phase})")
        (args.work / "development-sha256.json").write_text(json.dumps(reference, indent=2) + "\n", encoding="utf-8")
        print(f"DEV | {len(reference)}/{len(dev_classes)} zgodnych ścieżek i SHA-256 w trzech przebiegach, "
              "3/3 dokumenty konkursowe i 8/8 negatywów po 0 B w każdym przebiegu.")
        score_development(args, args.work / "development-konkurs", subset_manifest)
    else:
        print("Próba syntetyczna. Pełny odbiór obejmuje podzbiór DEV przekazany przez --dataset.")
    print(f"Dowody przebiegu: {args.work}")


if __name__ == "__main__":
    main()
