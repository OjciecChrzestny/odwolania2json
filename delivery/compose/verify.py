"""Porównanie publicznego CLI natywnie i w Docker Compose."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from evaluation.score import checked_file


ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT_SHA = "de135d20811caf630f3e94dc655ba5eebd9a6710"
OCR_SHA = "c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2"
INPUT = "PDF jurora"
DUPLICATE = "duplikat/doc_04.json"
PAYMENT = "case_10/doc_04.json"
NEGATIVE = "case_10/doc_02.json"
SCAN = "skany/doc_01.json"
COMPOSE = ["docker", "compose"]
HOST_VARIABLES = ("ODW_INPUT_DIR", "ODW_OUTPUT_PARENT", "ODW_OUTPUT_NAME", "ODW_DIAGNOSTICS_DIR")


def git_head(folder):
    return subprocess.check_output(
        ["git", "-C", str(folder), "rev-parse", "HEAD"], text=True
    ).strip()


def read_json(path):
    return json.loads(path.read_bytes())


def run(*command, env=None):
    print(subprocess.list2cmdline(map(str, command)), flush=True)
    start = perf_counter()
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    print(f"Czas: {perf_counter() - start:.3f} s", flush=True)


def case_rows():
    manifest = read_json(ROOT / "evaluation/development-40.json")
    return [row for row in manifest["documents"] if row["input"].startswith("case_10/")]


def prepare(dataset, source):
    assert git_head(dataset) == DEVELOPMENT_SHA, "Inna rewizja danych UZP"
    for row in case_rows():
        target = source / row["input"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(checked_file(dataset, row["pdf"], row["sha256"]), target)
    for directory in ("duplikat", "skany"):
        (source / directory).mkdir()
    shutil.copyfile(source / Path(PAYMENT).with_suffix(".pdf"), source / Path(DUPLICATE).with_suffix(".pdf"))
    shutil.copyfile(Path(__file__).with_name("skan-syntetyczny.pdf"), source / Path(SCAN).with_suffix(".pdf"))


def outputs(directory):
    return {path.relative_to(directory).as_posix(): path.read_bytes()
            for path in sorted(directory.rglob("*")) if path.is_file()}


def validate(directory, diagnostic):
    expected = {Path(row["input"]).with_suffix(".json").as_posix(): row["class"]
                for row in case_rows()}
    expected.update({DUPLICATE: "przelew", SCAN: "przelew"})
    results = outputs(directory)
    assert results.keys() == expected.keys(), sorted(results)
    assert results[NEGATIVE] == b"", "Negatyw musi mieć 0 bajtów"
    assert results[PAYMENT] == results[DUPLICATE], "Kopie przelewu dały różne bajty"
    scan_payment = json.loads(results[SCAN])["przelew_bankowy"]
    assert scan_payment["kwota"] == 123.45 and scan_payment["tytul"] == "Opłata za usługę", scan_payment
    records = {record["output"]: record for record in read_json(diagnostic)["documents"]}
    assert {name: record["class"] for name, record in records.items()} == expected, records.keys()
    assert records[SCAN]["ocr_pages"] == [1], records[SCAN]["ocr_pages"]
    print(f"Skan: kwota={scan_payment['kwota']}, tytul={scan_payment['tytul']}, ocr_pages=[1]")
    return results


def compare(expected, actual):
    assert sorted(expected) == sorted(actual), (sorted(expected), sorted(actual))
    for name in sorted(expected):
        assert expected[name] == actual[name], f"Różne bajty: {name}"


def native(work, tessdata):
    assert hashlib.sha256((tessdata / "pol.traineddata").read_bytes()).hexdigest() == OCR_SHA
    print(platform.platform(), sys.version.split()[0],
          *(f"{package}={version(package)}" for package in ("pypdf", "pypdfium2", "tesserocr")))
    output = work / "native/output"
    diagnostic = work / "native/diagnostics/last-run.json"
    for source, destination, log in (
        (work / INPUT, output, diagnostic),
        (work / "native/empty", work / "native/empty-output", work / "native/empty-diagnostics/last-run.json"),
    ):
        run(sys.executable, "-m", "odwolania2json", "--input", source,
            "--output", destination, "--diagnostics", log, "--ocr-data", tessdata)
    assert not outputs(work / "native/empty-output")
    assert read_json(work / "native/empty-diagnostics/last-run.json") == {"documents": []}
    validate(output, diagnostic)
    (work / "native/revision").write_text(git_head(ROOT), encoding="ascii")


def compose(work):
    assert (work / "native/revision").read_text(encoding="ascii") == git_head(ROOT), "Różne SHA"
    env = os.environ.copy()
    for name in HOST_VARIABLES:
        env.pop(name, None)
    run("docker", "version", env=env)
    run(*COMPOSE, "version", env=env)
    if os.name == "posix":
        security_options = json.loads(subprocess.check_output(
            ["docker", "info", "--format", "{{json .SecurityOptions}}"], env=env
        ))
        uid, gid = (0, 0) if "name=rootless" in security_options else (os.getuid(), os.getgid())
        env.update(ODW_UID=str(uid), ODW_GID=str(gid))
        print(f"Użytkownik kontenera: {uid}:{gid}", flush=True)
    revision = git_head(ROOT)
    image = f"odwolania2json-compose-verify:{uuid4().hex}"
    env["ODW_JURY_IMAGE"] = image
    run("docker", "build", "--target", "jury", "--tag", image,
        "--label", f"org.opencontainers.image.revision={revision}", ".", env=env)

    for directory in ("input", "output", ".output.odwolania2json", "diagnostics"):
        (ROOT / directory).mkdir()
    run(*COMPOSE, "run", "--rm", "-T", "--pull", "never", "cli", env=env)
    assert not outputs(ROOT / "output")
    assert read_json(ROOT / "diagnostics/last-run.json") == {"documents": []}

    output = work / "wyniki jurora"
    other = work / "inne wyniki"
    diagnostics = work / "diagnostyka jurora"
    source = work / INPUT

    def state(destination):
        return destination.with_name(f".{destination.name}.odwolania2json")

    def variables(destination):
        destination.mkdir(exist_ok=True)
        state(destination).mkdir(exist_ok=True)
        return env | {
            "ODW_INPUT_DIR": str(source),
            "ODW_OUTPUT_PARENT": str(destination.parent),
            "ODW_OUTPUT_NAME": destination.name,
            "ODW_DIAGNOSTICS_DIR": str(diagnostics),
        }

    diagnostics.mkdir()
    job = [*COMPOSE, "run", "--rm", "-T", "--pull", "never"]
    main_env = variables(output)
    probe = (
        "import errno, hashlib, socket, sys; from pathlib import Path; from importlib.metadata import version\n"
        f"assert hashlib.sha256(Path('/opt/tessdata/pol.traineddata').read_bytes()).hexdigest() == '{OCR_SHA}'\n"
        "assert {name for _, name in socket.if_nameindex()} == {'lo'}\n"
        "try:\n Path('/work/input/.write-test').touch()\n"
        "except OSError as exc:\n assert exc.errno == errno.EROFS, exc\n"
        "else:\n raise AssertionError('Katalog wejściowy dostępny do zapisu')\n"
        "print(sys.version.split()[0], *(f'{p}={version(p)}' for p in ('pypdf','pypdfium2','tesserocr')))\n"
        "print('Sprawdzono montaż tylko do odczytu, SHA pol.traineddata i brak interfejsu sieciowego poza lo')"
    )
    run(*job, "--entrypoint", "python", "cli", "-c", probe, env=main_env)

    log = diagnostics / "last-run.json"
    run(*job, "cli", env=main_env)
    original = validate(output, log)
    compare(outputs(work / "native/output"), original)
    compare({"last-run.json": (work / "native/diagnostics/last-run.json").read_bytes()},
            {"last-run.json": log.read_bytes()})
    for name, content in sorted(original.items()):
        print(f"{name} | {len(content)} B | {hashlib.sha256(content).hexdigest()}")

    run(*job, "cli", env=main_env)
    compare(original, validate(output, log))

    # Drugie wyjście zapisuje w swojej ewidencji wyłącznie skan.
    scan_input = work / "Tylko skan"
    (scan_input / "skany").mkdir(parents=True)
    shutil.copyfile(source / Path(SCAN).with_suffix(".pdf"), scan_input / Path(SCAN).with_suffix(".pdf"))
    other_env = variables(other) | {"ODW_INPUT_DIR": str(scan_input)}
    run(*job, "cli", env=other_env)
    compare({SCAN: original[SCAN]}, outputs(other))

    manual = b'{"autor":"juror"}\n'
    (output / "reczny.json").write_bytes(manual)
    changed = work / "PDF po zmianie"
    shutil.copytree(source, changed)
    (changed / Path(DUPLICATE).with_suffix(".pdf")).unlink()
    run(*job, "cli", env=main_env | {"ODW_INPUT_DIR": str(changed)})
    expected = original | {"reczny.json": manual}
    del expected[DUPLICATE]
    compare(expected, outputs(output))
    compare({SCAN: original[SCAN]}, outputs(other))
    assert read_json(state(output) / "owned") == sorted(original.keys() - {DUPLICATE})
    assert read_json(state(other) / "owned") == [SCAN]
    print("Zgodne ścieżki, bajty i diagnostyka A/Compose. Powtórzenie, pusty folder, osobne ewidencje i sprzątanie: OK.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path, help="nowy katalog przebiegu poza checkoutem")
    parser.add_argument("--dataset", type=Path, help="kopia rewizji rozwojowej UZP")
    parser.add_argument("--tessdata", type=Path, help="katalog pol.traineddata do natywnego A")
    parser.add_argument("--mode", choices=("both", "native", "compose"), default="both")
    args = parser.parse_args()
    work = args.work.resolve()
    print(f"Host: {platform.node()}, {platform.platform()} | SHA: {git_head(ROOT)}")
    if args.mode != "compose":
        if args.dataset is None or args.tessdata is None:
            parser.error("przebieg natywny wymaga --dataset i --tessdata")
        work.mkdir(parents=True)
        prepare(args.dataset.resolve(), work / INPUT)
        native(work, args.tessdata.resolve())
    if args.mode != "native":
        compose(work)


if __name__ == "__main__":
    main()
