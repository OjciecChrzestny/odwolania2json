"""Zapieczętuj i wykonaj jeden porównawczy przebieg na identycznych PDF-ach."""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from odwolania2json.model import load_classes

from .check_outputs import check_outputs, read_json
from .score import checked_file, fields, load_object, score
from .score_accounts import measure_accounts
from .score_review import is_relative_name, score_review

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "evaluation/protocol_06.json"
COHORTS = tuple(read_json(PROTOCOL)["cohorts"])
EVALUATOR = ("evaluation/protocol_06.json", "evaluation/compare_once.py", "evaluation/score.py",
             "evaluation/check_outputs.py", "evaluation/score_accounts.py",
             "evaluation/score_review.py", "evaluation/restrict_linux.c", "odwolania2json/model.py")
COORD = Path.home() / "uzp-parallel/koordynacja"
REGISTRY = COORD / "runda-96f88b6/06-porownanie"
LOCKS = COORD / "runda-ae0bae4/blokady"


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def encoded(doc):
    return (json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def save(path, value):
    staging = path.with_suffix(".tmp")
    staging.write_bytes(encoded(value))
    staging.replace(path)


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def evaluator_hashes():
    configs = sorted((ROOT / "odwolania2json/classes").glob("*.json"))
    return {str(path.relative_to(ROOT)): digest(path)
            for path in [*(ROOT / name for name in EVALUATOR), *configs]}


def verify_revision(revision):
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or git(
        "rev-parse", "--verify", f"{revision}^{{commit}}"
    ).decode().strip() != revision:
        raise ValueError("Podaj pełny SHA istniejącego commita.")
    return revision


def runtime(python, ocr_data=None, ocr_lock=None):
    python = Path(python).absolute()
    packages = ["pypdf"] + (["pypdfium2", "tesserocr"] if ocr_data else [])
    probe = ("import importlib.metadata as m, json, sys; "
             "print(json.dumps({'python':sys.version, 'prefix':sys.prefix, 'base':sys.base_prefix, "
             "'packages':{name:m.version(name) for name in sys.argv[1:]}}))")
    info = json.loads(subprocess.check_output([python, "-I", "-B", "-c", probe, *packages]))
    info.update(executable=str(python), executable_sha256=digest(python))
    if ocr_data:
        ocr_data = Path(ocr_data).resolve()
        ocr_lock = Path(ocr_lock).resolve()
        if ocr_lock not in {LOCKS / "ocr-1.lock", LOCKS / "ocr-2.lock"} or not ocr_lock.is_file():
            raise ValueError("OCR wymaga jednej z dwóch istniejących blokad rundy.")
        info.update(ocr_data=str(ocr_data), ocr_sha256=digest(ocr_data / "pol.traineddata"),
                    ocr_lock=str(ocr_lock))
    return info


def manifest_rows(cohort):
    path = Path(cohort["manifest"])
    if digest(path) != cohort["manifest_sha256"]:
        raise ValueError(f"SHA-256 manifestu niezgodny z pieczęcią: {path}")
    rows = read_json(path)["documents"]
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Pusty manifest: {path}")
    names = set()
    for row in rows:
        source = row["input"]
        if not is_relative_name(source) or Path(source).suffix.lower() != ".pdf":
            raise ValueError(f"Nieprawidłowa neutralna ścieżka PDF: {source!r}")
        output = Path(source).with_suffix(".json")
        if (output in names or not is_relative_name(row["pdf"])
                or row["reference"] is not None and not is_relative_name(row["reference"])):
            raise ValueError(f"Powtórzona ścieżka lub błędne mapowanie: {source}")
        names.add(output)
    return rows


def ensure_private(cohort, rows, info):
    allowed = [Path("/usr"), Path(info["prefix"]).resolve(), Path(info["base"]).resolve()]
    if info.get("ocr_data"):
        allowed.append(Path(info["ocr_data"]))
    dataset = Path(cohort["dataset"])
    private = [Path(cohort["manifest"]), dataset]
    private.extend(dataset / row["reference"] for row in rows if row["reference"] is not None)
    if any(path.resolve().is_relative_to(root) for path in private for root in allowed):
        raise ValueError("Manifest lub etykieta znajduje się w katalogu dostępnym dla ekstraktora.")


def prepare_seal(args):
    spec = read_json(args.spec)
    mode = spec["mode"]
    cohorts = spec["cohorts"]
    if mode not in ("synthetic", "production") or not cohorts or not cohorts.keys() <= set(COHORTS):
        raise ValueError("Nieznana grupa lub tryb porównania.")
    protocol = read_json(PROTOCOL)
    if mode == "production":
        if set(cohorts) != set(COHORTS) or args.baseline != protocol["frozen_baseline_sha"]:
            raise ValueError("Przebieg produkcyjny wymaga pełnego zestawu grup i bazy z protokołu.")
    if args.baseline == args.candidate:
        raise ValueError("Porównanie wymaga dwóch osobnych, pełnych SHA.")
    revisions = {"baseline": verify_revision(args.baseline), "candidate": verify_revision(args.candidate)}
    subprocess.run(["git", "-C", ROOT, "merge-base", "--is-ancestor", args.baseline, args.candidate], check=True)
    info = runtime(args.python, args.ocr_data, args.ocr_lock)
    for name, cohort in cohorts.items():
        if cohort["labels"] not in (("synthetic",) if mode == "synthetic" else ("human", "unavailable")):
            raise ValueError(f"{name}: poświadcz pochodzenie adnotacji stron i kontroli.")
        cohort["dataset"] = str(Path(cohort["dataset"]).resolve())
        cohort["manifest"] = str(Path(cohort["manifest"]).resolve())
        rows = manifest_rows(cohort)
        ensure_private(cohort, rows, info)
        if mode == "production" and name == "known_128" and Counter(row["class"] for row in rows) != {
            "odwolanie": 40, "pelnomocnictwo": 40, "przelew": 40, "negative": 8
        }:
            raise ValueError("Znane 128 wymaga podziału 40/40/40/8.")
        cohort["documents"] = len(rows)
        cohort["inputs"] = {row["input"]: row["sha256"] for row in rows}
        for row in rows:
            checked_file(Path(cohort["dataset"]), row["pdf"], row["sha256"])
    seal = dict(version=1, frozen_utc=now(), mode=mode, revisions=revisions, cohorts=cohorts,
                evaluator=evaluator_hashes(), runtime=info)
    with args.seal.open("xb") as target:
        target.write(encoded(seal))
    print(f"{digest(args.seal)}  {args.seal}")


def archive_product(revision, destination):
    destination.mkdir()
    package = git("archive", "--format=tar", revision, "odwolania2json")
    with tarfile.open(fileobj=io.BytesIO(package)) as archive:
        if any(not (item.isfile() or item.isdir()) for item in archive.getmembers()):
            raise ValueError(f"{revision}: archiwum produktu zawiera dowiązanie lub specjalny plik.")
        archive.extractall(destination, filter="data")


def staged_inputs(cohort, rows, job):
    input_dir = job / "input"
    input_dir.mkdir(parents=True)
    for row in rows:
        source = checked_file(Path(cohort["dataset"]), row["pdf"], row["sha256"])
        target = input_dir / row["input"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if digest(target) != cohort["inputs"][row["input"]]:
            raise ValueError(f"Zmienione wejście: {row['input']}")
    for directory in ("output", "diagnostics", ".output.odwolania2json"):
        (job / directory).mkdir()


def restricted_command(restrict, info, product, job):
    runtime_paths = ["/usr", "/etc/ld.so.cache", "/dev/null", "/dev/urandom",
                     info["prefix"], info["base"], product, job / "input"]
    if "ocr_data" in info:
        runtime_paths.append(info["ocr_data"])
    command = [str(restrict)]
    for path in runtime_paths:
        command.extend(["-r", str(path)])
    for name in ("output", "diagnostics", ".output.odwolania2json"):
        command.extend(["-w", str(job / name)])
    return [*command, "--", info["executable"], "-B"]


def extract(restrict, info, product, job, secret):
    command = restricted_command(restrict, info, product, job)
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8", "OMP_THREAD_LIMIT": "1",
           "PYTHONNOUSERSITE": "1"}
    probe = ("import pathlib, socket, sys\n"
             "try: pathlib.Path(sys.argv[1]).read_bytes()\n"
             "except PermissionError: pass\n"
             "else: sys.exit('Próba odczytu etykiety nie została zablokowana')\n"
             "with socket.socket() as sock:\n"
             "    try: sock.bind(('127.0.0.1', 0))\n"
             "    except PermissionError: pass\n"
             "    else: sys.exit('Dostęp TCP nie został zablokowany')\n")
    subprocess.run([*command, "-c", probe, str(secret)], cwd=product, env=env, check=True)
    command.extend(["-m", "odwolania2json", "--input", str(job / "input"), "--output",
                    str(job / "output"), "--diagnostics", str(job / "diagnostics/extraction.json")])
    if "ocr_data" in info:
        command = ["flock", info["ocr_lock"], *command, "--ocr-data", info["ocr_data"]]
    save(job / "extract-command.json", {"argv": command, "env": env, "cwd": str(product)})
    with (job / "extract.log").open("wb") as log:
        result = subprocess.run(command, cwd=product, env=env, stdout=log, stderr=subprocess.STDOUT)
    save(job / "extract-status.json", {"exit_code": result.returncode, "finished_utc": now()})
    if result.returncode not in (0, 1) or not (job / "diagnostics/extraction.json").is_file():
        raise RuntimeError(f"Awaria ekstrakcji w {job}, kod {result.returncode}.")

def inventory(folder):
    return {path.relative_to(folder).as_posix(): digest(path)
            for path in sorted(folder.rglob("*")) if path.is_file()}


def as_fields(path):
    try:
        return set(fields(load_object(path)))
    except (OSError, ValueError):
        return set()


def paths(atoms):
    # Paths and types suffice to review regressions. Keep document values in the original evidence.
    result = [{"path": list(path), "kind": kind} for path, kind, _ in atoms]
    return sorted(result, key=lambda item: json.dumps(item, ensure_ascii=False))


def gold_deltas(dataset, rows, baseline, candidate):
    changed = []
    old_hashes, new_hashes = inventory(baseline), inventory(candidate)
    for row in rows:
        name = Path(row["input"]).with_suffix(".json").as_posix()
        if old_hashes.get(name) == new_hashes.get(name):
            continue
        expected = set()
        if row["reference"] is not None:
            label = checked_file(dataset, row["reference"], row["reference_sha256"], reference=True)
            expected = set(fields(load_object(label)))
        old, new = as_fields(baseline / name), as_fields(candidate / name)
        changed.append({"output": name, "class": row["class"], "baseline_sha256": old_hashes.get(name),
                        "candidate_sha256": new_hashes.get(name), "recovered": paths((new - old) & expected),
                        "lost": paths((old - new) & expected), "spurious_added": paths(new - old - expected),
                        "spurious_removed": paths(old - new - expected)})
    extras = (old_hashes.keys() | new_hashes.keys()) - {
        Path(row["input"]).with_suffix(".json").as_posix() for row in rows
    }
    return {"expected_documents": len(rows), "changed_expected_outputs": changed,
            "extra_outputs": {name: {"baseline_sha256": old_hashes.get(name),
                                    "candidate_sha256": new_hashes.get(name)} for name in sorted(extras)}}


def classification(matrix):
    classes = {}
    for label, row in matrix.items():
        tp = row[label]
        classes[label] = {"tp": tp, "fn": sum(row.values()) - tp,
                          "fp": sum(other[label] for name, other in matrix.items() if name != label),
                          "support": sum(row.values())}
    return {"correct": sum(counts["tp"] for counts in classes.values()),
            "denominator": sum(counts["support"] for counts in classes.values()),
            "by_class": classes}


def evaluate(name, cohort, rows, job):
    dataset, manifest = Path(cohort["dataset"]), Path(cohort["manifest"])
    output = job / "output"
    diagnostics = job / "diagnostics/extraction.json"
    config = ROOT / "odwolania2json/classes"
    field = score(dataset, output, manifest)
    contract = check_outputs(output, {"documents": rows}, read_json(diagnostics), load_classes(config))
    result = {"fields": field, "contract": contract, "classification": classification(contract["confusion_matrix"]),
              "score_status": "measured" if field["valid_run"] and contract["valid_contract"] else "diagnostic"}
    if name == "blind_transfers":
        accounts = measure_accounts(dataset, output, {"documents": rows})
        accounts["single_opposite_account_documents"] = accounts["opposite_role_fields"] - 2 * accounts["complete_swaps"]
        result["accounts"] = accounts
    if name == "page_review":
        result["review"] = None
        result["review_status"] = "unavailable_without_independent_human_labels"
        if cohort["labels"] in ("human", "synthetic"):
            review = score_review(dataset, output, manifest, diagnostics, config)
            result["review"] = review
            result["review_status"] = "synthetic" if cohort["labels"] == "synthetic" else "measured"
            result["profiles"] = {
                profile: {
                    "incorrect_auto": data["decision_matrix"]["incorrect"]["auto_accepted"],
                    "auto_denominator": data["acceptance_accuracy"]["denominator"],
                    "disposition": "coordinator_review" if (
                        cohort["labels"] == "human" and review["valid_run"] and contract["valid_contract"]
                        and data["pages"]["unreadable_recall"]["denominator"] > 0
                        and data["acceptance_accuracy"]["denominator"] > 0
                        and data["decision_matrix"]["incorrect"]["auto_accepted"] == 0
                    ) else "review_required",
                }
                for profile, data in review["by_profile"].items()
            }
    save(job / "evaluation.json", result)
    return {key: field[key] for key in ("tp", "fp", "fn", "micro_f1", "valid_run")}


def authorize(args, seal_digest, mode):
    if mode == "synthetic":
        return None
    if mode != "production" or args.approval is None:
        raise ValueError("Wymagana zgoda koordynatora na zamrożony przebieg produkcyjny.")
    approval = read_json(args.approval)
    if approval.get("decision") != "approved" or approval.get("seal_sha256") != seal_digest:
        raise ValueError("Zgoda nie obejmuje tej pieczęci.")
    return approval


def run_once(args):
    seal_raw = args.seal.read_bytes()
    seal_digest = hashlib.sha256(seal_raw).hexdigest()
    if seal_digest != args.seal_sha256:
        raise ValueError("Niezgodny SHA-256 pieczęci.")
    seal = json.loads(seal_raw)
    if seal["version"] != 1 or seal["evaluator"] != evaluator_hashes():
        raise ValueError("Niezgodna wersja pieczęci lub zmieniony kod miernika.")
    mode = seal["mode"]
    approval = authorize(args, seal_digest, mode)
    info = seal["runtime"]
    if info != runtime(info["executable"], info.get("ocr_data"), info.get("ocr_lock")):
        raise ValueError("Runtime różni się od zamrożonego.")
    for revision in seal["revisions"].values():
        verify_revision(revision)
    root = args.trial_root.resolve() if mode == "synthetic" else REGISTRY
    root.mkdir(parents=True, exist_ok=True)
    directory = root / (f"synthetic-{seal_digest}" if mode == "synthetic" else "production-attempt")
    directory.mkdir()
    (directory / "seal.json").write_bytes(seal_raw)
    if approval:
        save(directory / "approval.json", approval)
    save(directory / "state.json", {"state": "started", "utc": now()})
    try:
        comparison = run_jobs(seal, directory)
        save(directory / "comparison.json", comparison)
    except Exception as exc:
        save(directory / "state.json", {"state": "failed", "utc": now(), "error": str(exc)})
        raise
    save(directory / "state.json", {"state": "completed", "utc": now()})
    print(directory / "comparison.json")


def run_jobs(seal, directory):
    restrict = directory / "restrict-linux"
    subprocess.run(["cc", "-O2", "-Wall", "-o", restrict, ROOT / "evaluation/restrict_linux.c"], check=True)
    private = directory / "evaluator-only"
    private.mkdir()
    secret = private / "label-probe"
    secret.write_text("Only the scoring process may read this file.", encoding="utf-8")
    products, batches = {}, {}
    for tag, revision in seal["revisions"].items():
        products[tag] = directory / f"product-{tag}"
        archive_product(revision, products[tag])
    for name, original in seal["cohorts"].items():
        rows = manifest_rows(original)
        ensure_private(original, rows, seal["runtime"])
        frozen_manifest = private / f"{name}.json"
        shutil.copyfile(original["manifest"], frozen_manifest)
        cohort = {**original, "manifest": str(frozen_manifest)}
        manifest_rows(cohort)
        batches[name] = (cohort, rows)
        for tag, product in products.items():
            job = directory / name / tag
            staged_inputs(cohort, rows, job)
            extract(restrict, seal["runtime"], product, job, secret)
            save(job / "outputs.sha256.json", inventory(job / "output"))
            save(job / "diagnostics.sha256.json", inventory(job / "diagnostics"))

    # Open field labels only once both variants and every cohort have finished extraction.
    result = {"revisions": seal["revisions"], "mode": seal["mode"], "cohorts": {}}
    for name, (cohort, rows) in batches.items():
        jobs = {tag: directory / name / tag for tag in products}
        manifest_rows(cohort)
        for job in jobs.values():
            for folder, record in (("output", "outputs.sha256.json"), ("diagnostics", "diagnostics.sha256.json")):
                if inventory(job / folder) != read_json(job / record):
                    raise ValueError(f"Zapis przebiegu zmienił się przed oceną: {job / folder}")
        local = {tag: evaluate(name, cohort, rows, job) for tag, job in jobs.items()}
        before, after = (local[tag] for tag in ("baseline", "candidate"))
        delta = {key: after[key] - before[key] for key in ("tp", "fp", "fn")}
        delta["micro_f1"] = None if None in (after["micro_f1"], before["micro_f1"]) else (
            after["micro_f1"] - before["micro_f1"]
        )
        delta.update(gold_deltas(Path(cohort["dataset"]), rows,
                                jobs["baseline"] / "output", jobs["candidate"] / "output"))
        result["cohorts"][name] = {"scores": local, "candidate_minus_baseline": delta}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--spec", type=Path, required=True)
    freeze.add_argument("--seal", type=Path, required=True)
    freeze.add_argument("--baseline", required=True)
    freeze.add_argument("--candidate", required=True)
    freeze.add_argument("--python", default=sys.executable)
    freeze.add_argument("--ocr-data")
    freeze.add_argument("--ocr-lock")
    run = commands.add_parser("run")
    run.add_argument("--seal", type=Path, required=True)
    run.add_argument("--seal-sha256", required=True)
    run.add_argument("--approval", type=Path)
    run.add_argument("--trial-root", type=Path, default=REGISTRY / "trials")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == "freeze":
            if bool(args.ocr_data) != bool(args.ocr_lock):
                parser.error("Podaj jednocześnie --ocr-data i --ocr-lock.")
            prepare_seal(args)
        else:
            run_once(args)
    except FileExistsError as exc:
        parser.exit(2, f"Pieczęć lub próba już istnieje: {exc.filename}\n")
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"Porównanie zatrzymane: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
