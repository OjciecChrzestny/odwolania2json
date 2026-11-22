"""Pokaz nowej klasy dokumentu i zagnieżdżonego obiektu na jednym obrazie CLI."""
import argparse
import difflib
import json
import os
import shutil
import subprocess
from pathlib import Path

from accept import (DEFAULT_CONFIG, EXTRA_CLASS, development_input, equal, profile_files,
                    results, score_development, sha, synthetic)
from pokaz import HERE, write_pdf

LOCATION = HERE / "miejsce_posiedzenia.json"


def prepare_input(directory):
    directory.mkdir()
    heading = "ZAWIADOMIENIE"
    sygnatura = "Sygnatura: KIO-DEMO/47/26"
    termin = "Termin: 9 lutego 2027"
    budynek, sala = "Budynek: Alfa", "Sala: 207"
    for filename, title, room_lines in (
        ("p01.pdf", heading, (sala,)),
        ("p02.pdf", heading, ()),
        ("p03.pdf", "KOMUNIKAT ORGANIZACYJNY", (sala,)),
    ):
        write_pdf(directory / filename, [
            (title, sygnatura, "Posiedzenie dotyczy rozpoznania zlozonego odwolania.",
             "Niniejszy dokument zostal przygotowany do jawnej proby technicznej."),
            ("MIEJSCE POSIEDZENIA", budynek, *room_lines, termin,
             "Dodatkowe informacje organizacyjne udostepnia sekretariat."),
        ])

    basic = {
        "result": {"sygnatura": "KIO-DEMO/47/26", "termin": "2027-02-09"},
        "signals": [{"rule": rule, "page": 1}
                    for rule in ("naglowek_zawiadomienia", "etykieta_sygnatury")],
        "fields": {
            "sygnatura": {"page": 1, "rule": "wiersz_sygnatury"},
            "termin": {"page": 2, "rule": "wiersz_terminu"},
        },
        "source_lines": {"sygnatura": sygnatura, "termin": termin},
    }
    notices = {"p01.json": basic, "p02.json": basic, "p03.json": None}
    locations = {}
    for filename, room in (("p01.json", "207"), ("p02.json", None)):
        fields = {"miejsce_posiedzenia.budynek": {"page": 2, "rule": "wiersz_budynek"}}
        lines = {"miejsce_posiedzenia.budynek": budynek}
        if room is not None:
            fields["miejsce_posiedzenia.sala"] = {"page": 2, "rule": "wiersz_sala"}
            lines["miejsce_posiedzenia.sala"] = sala
        locations[filename] = {
            **basic,
            "result": {**basic["result"], "miejsce_posiedzenia": {"budynek": "Alfa", "sala": room}},
            "fields": {**basic["fields"], **fields},
            "source_lines": {**basic["source_lines"], **lines},
        }
    return notices, {**locations, "p03.json": None}


def profiles(work):
    config = work / "klasy"
    shutil.copytree(DEFAULT_CONFIG, config)
    stock = profile_files(DEFAULT_CONFIG)
    equal(set(stock), {"odwolanie.json", "pelnomocnictwo.json", "przelew.json"}, "Trzy klasy konkursowe")
    yield "konkurs", None

    notice = config / EXTRA_CLASS.name
    shutil.copyfile(EXTRA_CLASS, notice)
    equal(profile_files(config), {**stock, notice.name: sha(EXTRA_CLASS)}, "Dodanie jednej klasy")
    print(f"+ {notice.name}", flush=True)
    yield "klasa", config

    before = notice.read_text(encoding="utf-8")
    class_config = json.loads(before)
    fragment = json.loads(LOCATION.read_bytes())
    for section in ("schema", "fields"):
        equal(class_config[section].keys() & fragment[section].keys(), set(), f"Nowe klucze {section}")
        class_config[section].update(fragment[section])
    expanded = json.dumps(class_config, ensure_ascii=False, indent=2) + "\n"
    notice.write_text(expanded, encoding="utf-8")
    equal(profile_files(config), {**stock, notice.name: sha(notice)}, "Zmiana tylko konfiguracji zawiadomienia")
    diff = difflib.unified_diff(before.splitlines(keepends=True), expanded.splitlines(keepends=True),
                                "klasa/zawiadomienie.json", "obiekt/zawiadomienie.json")
    (work / "roznica-obiektu.diff").write_text("".join(diff), encoding="utf-8")
    print(f"+ miejsce_posiedzenia | {work / 'roznica-obiektu.diff'}", flush=True)
    yield "obiekt", config

    notice.unlink()
    equal(profile_files(config), stock, "Przywrócenie trzech klas")
    yield "powrot", config


def run_cli(args, image, input_dir, target, config):
    output, diagnostics, journal = (target / name for name in ("output", "diagnostics", ".output.odwolania2json"))
    target.mkdir()
    for folder in (output, diagnostics, journal):
        folder.mkdir()
    command = [
        args.docker, "run", "--rm", "--pull", "never", "--network", "none", "--read-only",
        "--user", args.user, "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--env", "OMP_THREAD_LIMIT=1",
    ]
    for host, container in ((input_dir, "/work/input:ro"), (output, "/work/output"),
                            (diagnostics, "/work/diagnostics"), (journal, "/work/.output.odwolania2json")):
        command += ["--volume", f"{host}:{container}"]
    if config is not None:
        command += ["--volume", f"{config}:/work/klasy:ro"]
    command.append(image)
    if config is not None:
        command += ["--config", "/work/klasy"]
    subprocess.run(command, check=True)
    rows = json.loads((diagnostics / "last-run.json").read_bytes())["documents"]
    records = {row["output"]: row for row in rows}
    equal(len(records), len(rows), f"Unikatowe rekordy {target.name}")
    return output, records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path, help="nowy katalog przebiegu")
    parser.add_argument("--image", required=True, help="gotowy lokalny obraz CLI")
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--user", default=f"{os.getuid()}:{os.getgid()}", help="UID:GID kontenera, dla Docker rootless 0:0")
    parser.add_argument("--pdf", type=Path, help="opcjonalny własny PDF z warstwą tekstową")
    parser.add_argument("--tylko-pdf", action="store_true",
                        help="pomiń generowanie syntetyków, użyj na hoście biblioteki standardowej")
    parser.add_argument("--dataset", type=Path, help="opcjonalna przypięta kopia DEV do regresji 11 PDF-ów")
    args = parser.parse_args()
    args.work = args.work.resolve()
    if args.dataset:
        args.dataset = args.dataset.resolve()
    if args.tylko_pdf and not args.pdf:
        parser.error("--tylko-pdf wymaga --pdf")
    if args.pdf and (not args.pdf.is_file() or args.pdf.suffix.lower() != ".pdf"):
        parser.error("--pdf wymaga istniejącego pliku PDF")

    image = subprocess.check_output(
        [args.docker, "image", "inspect", "--format", "{{.Id}}", args.image], text=True,
    ).strip()
    args.work.mkdir()
    (args.work / "obraz.txt").write_text(f"{image}\n", encoding="utf-8")
    print(f"Obraz | {image}", flush=True)
    input_dir = args.work / "input"
    if not args.tylko_pdf:
        notices, locations = prepare_input(input_dir)
    dev_input = args.work / "development-pdf"
    subset = args.work / "development-manifest.json"
    if args.dataset:
        dev_classes = development_input(args.dataset, dev_input, subset)
    custom_input = args.work / "input-jurora"
    if args.pdf:
        custom_input.mkdir()
        shutil.copyfile(args.pdf, custom_input / "p04.pdf")

    samples, custom, dev = {}, {}, {}
    for phase, config in profiles(args.work):
        print(f"\nProfil {phase}", flush=True)
        if not args.tylko_pdf:
            output, records = run_cli(args, image, input_dir, args.work / phase, config)
            expected = locations if phase == "obiekt" else notices
            samples[phase] = synthetic(input_dir, output, records, expected, phase in {"klasa", "obiekt"})
        if args.pdf:
            output, records = run_cli(args, image, custom_input, args.work / f"juror-{phase}", config)
            result = output / "p04.json"
            custom[phase] = sha(result)
            print(f"p04.json | {records[result.name]['class']} | {result.stat().st_size} B", flush=True)
        if args.dataset:
            output, records = run_cli(args, image, dev_input, args.work / f"development-{phase}", config)
            dev[phase] = results(output, records, dev_classes)

    if samples:
        equal(samples["powrot"], samples["konkurs"], "Powrót syntetyków do profilu konkursowego")
    if custom:
        equal(custom["powrot"], custom["konkurs"], "Powrót własnego PDF-u do profilu konkursowego")
        print("Własny PDF | wynik po powrocie identyczny bajtowo z pierwszym przebiegiem.")
    if args.dataset:
        reference = dev["konkurs"]
        for phase in ("klasa", "obiekt", "powrot"):
            equal(dev[phase], reference, f"Ścieżki i SHA-256 DEV ({phase})")
        (args.work / "development-sha256.json").write_text(json.dumps(reference, indent=2) + "\n", encoding="utf-8")
        score_development(args, args.work / "development-konkurs/output", subset)
        print(f"DEV | {len(reference)}/{len(dev_classes)} identycznych wyników w czterech profilach, "
              "3/3 klasy i 8/8 negatywów po 0 B.")
    print(f"Dowody przebiegu: {args.work}")


if __name__ == "__main__":
    main()
