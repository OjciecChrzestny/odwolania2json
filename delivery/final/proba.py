"""Próba jurora na świeżych syntetykach i publicznym CLI wybranej rewizji."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

CONFIG_PATH = "demo/rozszerzalnosc/zawiadomienie.json"
FONT = "/usr/share/fonts/truetype/lato/Lato-Regular.ttf"
AMOUNT_LINE = "Kwota: 123,45 PLN"
REVIEW_FIELD = "przelew_bankowy.numer_transakcji"
STAGE_FILES = {
    "przygotuj": ("input/*.pdf", "rozszerzenie/input/*.pdf"),
    "przelew": ("domyslne/output/*.json", "domyslne/diagnostics/last-run.json"),
    "klasa": (
        "rozszerzenie/klasy/*.json",
        "rozszerzenie/przed/output/*.json", "rozszerzenie/przed/diagnostics/last-run.json",
        "rozszerzenie/demo/output/*.json", "rozszerzenie/demo/diagnostics/last-run.json",
        "regresja/output/*.json", "regresja/diagnostics/last-run.json",
    ),
}
QUALITY_CORPORA = {"rozwojowy", "niezalezny"}
CLASS_BY_FILE = {
    "doc_01.json": "przelew",
    "doc_02.json": "negative",
    "doc_03.json": "odwolanie",
    "doc_04.json": "pelnomocnictwo",
    "doc_05.json": "przelew",
}
TRANSFER = {
    "data_operacji": "2026-11-21",
    "kwota": 123.45,
    "tytul": "Wpis za odwołanie",
    "numer_transakcji": "0000123",
    "z_rachunku": "00123456789012345678901234",
    "na_rachunek": "00987654321098765432109876",
}


def verify(actual, expected, label):
    if actual != expected:
        raise ValueError(f"{label}: otrzymano {actual!r}, oczekiwano {expected!r}")


def make_pdf(path, heading, lines):
    pdf = canvas.Canvas(str(path), pagesize=(595, 842), invariant=1)
    pdf.setFont("Próba", 12)
    pdf.drawString(52, 790, "MATERIAŁ FIKCYJNY")
    pdf.setFont("Próba", 25)
    pdf.drawString(52, 735, heading)
    body = pdf.beginText(52, 680)
    body.setFont("Próba", 17, 27)
    for line in lines:
        body.textLine(line)
    pdf.drawText(body)
    pdf.drawString(52, 50, "Strona 1 z 1")
    pdf.save()


def prepare(args):
    args.work.mkdir()
    source = args.work / "input"
    source.mkdir()
    invoke([sys.executable, args.repo / "demo/rozszerzalnosc/pokaz.py", "przygotuj",
            args.work / "rozszerzenie"], args.repo)
    pdfmetrics.registerFont(TTFont("Próba", FONT))
    transfer_lines = [
        "Data operacji: 21 listopada 2026",
        AMOUNT_LINE,
        "Z rachunku: " + TRANSFER["z_rachunku"],
        "Na rachunek: " + TRANSFER["na_rachunek"],
        "Tytuł: Wpis za odwołanie",
    ]
    make_pdf(source / "doc_01.pdf", "Potwierdzenie przelewu",
             [*transfer_lines, "Numer transakcji: " + TRANSFER["numer_transakcji"]])
    make_pdf(source / "doc_05.pdf", "Potwierdzenie przelewu", transfer_lines)
    make_pdf(source / "doc_02.pdf", "Wezwanie do zapłaty", [
        "Termin: 26 listopada 2026",
        "Kwota: 123,45 PLN",
        "Rachunek odbiorcy: 00987654321098765432109876",
    ])
    make_pdf(source / "doc_03.pdf", "ODWOŁANIE", [
        "Krajowa Izba Odwoławcza",
        "Odwołujący: Przykładowa Firma, NIP 0001234567",
        "Zamawiający: Przykładowa Gmina",
        "Zarzut nr 1: zaniechanie odrzucenia oferty.",
    ])
    make_pdf(source / "doc_04.pdf", "PEŁNOMOCNICTWO", [
        "Przykładowa Firma, NIP 0001234567,",
        "udziela pełnomocnictwa: adw. Anna Przykładowa.",
        "Pełnomocnictwo przyjmuję:",
        ".............................",
        "adw. Anna Przykładowa",
    ])
    print(f"Syntetyczne wejście: {source}", flush=True)


def invoke(command, cwd, capture=False):
    run = subprocess.run(command, cwd=cwd, check=True, text=True,
                         encoding="utf-8", capture_output=capture)
    return run.stdout


def git(repo, *args):
    return invoke(["git", "-C", repo, *args], repo, capture=True).strip()


def cli(args, inputs, target, config=None):
    target.mkdir()
    output, diagnostics = target / "output", target / "diagnostics"
    output.mkdir()
    diagnostics.mkdir()
    journal = target / ".output.odwolania2json"
    journal.mkdir()
    diagnostic_file = diagnostics / "last-run.json"
    if args.image:
        command = [args.docker, "run", "--rm", "--network", "none", "--pull", "never",
                   "--read-only", "--user", "0:0", "--cap-drop", "ALL",
                   "--env", "OMP_THREAD_LIMIT=1",
                   "--security-opt", "no-new-privileges"]
        mounts = [
            (inputs, "/work/input,readonly"), (output, "/work/output"),
            (diagnostics, "/work/diagnostics"), (journal, "/work/.output.odwolania2json"),
        ]
        if config:
            mounts.append((config, "/work/klasy,readonly"))
        for host, container in mounts:
            command += ["--mount", f"type=bind,src={host},dst={container}"]
        command += [args.image]
        if config:
            command += ["--config", "/work/klasy"]
    else:
        command = [sys.executable, "-m", "odwolania2json", "--input", inputs,
                   "--output", output, "--diagnostics", diagnostic_file]
        if config:
            command += ["--config", config]
    display = "python -m odwolania2json"
    if config:
        display += " --config KATALOG_KLAS"
    print(f"$ {display}", flush=True)
    started = perf_counter()
    invoke(command, args.repo)
    elapsed = perf_counter() - started
    records = json.loads(diagnostic_file.read_bytes())["documents"]
    return output, {row["output"]: row for row in records}, elapsed


def source_view(pdf, records, field, expected_page, expected_rule, expected_line):
    item = records[pdf.with_suffix(".json").name]["fields"][field]
    verify(item["page"], expected_page, field)
    verify(item["rule"], expected_rule, field)
    page_text = PdfReader(pdf).pages[item["page"] - 1].extract_text()
    line = next((line for line in page_text.splitlines() if line == expected_line), None)
    verify(line, expected_line, f"Tekst {pdf.name}")
    print(f"{pdf.name} | strona {item['page']} | {field} → {item['rule']}\n{line}")


def check_outputs(output, records, expected):
    verify({name: row["class"] for name, row in records.items()}, expected, "Klasy dokumentów")
    verify(sorted(path.name for path in output.iterdir()), sorted(expected), "Ścieżki JSON")
    for name, label in expected.items():
        negative = label == "negative"
        verify(records[name]["status"], "negative" if negative else "ok", name)
        verify((output / name).stat().st_size == 0, negative, name)
    return {name: digest(output / name) for name in expected}


def transfer(args):
    source, target = args.work / "input", args.work / "domyslne"
    output, records, elapsed = cli(args, source, target)
    check_outputs(output, records, CLASS_BY_FILE)
    verify(json.loads((output / "doc_01.json").read_bytes()), {"przelew_bankowy": TRANSFER}, "Przelew")
    print((output / "doc_01.json").read_text(encoding="utf-8"), end="", flush=True)
    print("doc_02.json: 0 B", flush=True)
    source_view(source / "doc_01.pdf", records, "przelew_bankowy.kwota", 1,
                "kwota_operacji", AMOUNT_LINE)
    review = json.loads((output / "doc_05.json").read_bytes())
    verify(review, {"przelew_bankowy": {**TRANSFER, "numer_transakcji": None}}, "Ręczna kontrola")
    verify(REVIEW_FIELD in records["doc_05.json"]["fields"], False, "Dowód brakującego pola")
    print("Kontrola prezentera | doc_05.pdf | numer_transakcji: null | brak wartości w PDF-ie")
    return {"cli_domyslne": elapsed}


def extension(args):
    work, root = args.work, args.work / "rozszerzenie"
    configuration = root / "klasy"
    before_output, before_records, before_time = cli(args, root / "input", root / "przed")
    check_outputs(before_output, before_records, {
        "doc_01.json": "negative", "doc_02.json": "negative", "doc_03.json": "negative",
    })
    print("Bez dodatkowej klasy: 3/3 puste wyniki.")
    before = {file.name: digest(file) for file in configuration.glob("*.json")}
    builtin = args.repo / "odwolania2json/classes"
    verify(before, {file.name: digest(file) for file in builtin.glob("*.json")}, "Klasy wbudowane")
    shutil.copyfile(args.repo / CONFIG_PATH, configuration / "zawiadomienie.json")
    after = {file.name: digest(file) for file in configuration.glob("*.json")}
    verify(after, {**before, "zawiadomienie.json": digest(args.repo / CONFIG_PATH)},
           "Zmiana konfiguracji")
    print(f"Dodany plik konfiguracji: {CONFIG_PATH}", flush=True)
    target = root / "demo"
    output, records, elapsed = cli(args, root / "input", target, configuration)
    check_outputs(output, records, {
        "doc_01.json": "zawiadomienie", "doc_02.json": "zawiadomienie", "doc_03.json": "negative",
    })
    for name, expected in [
        ("doc_01.json", {"sygnatura": "KIO-DEMO/17/26", "termin": "2026-12-03"}),
        ("doc_02.json", {"sygnatura": "KIO-DEMO/42/27", "termin": "2027-01-18"}),
    ]:
        result = (output / name).read_bytes()
        verify(json.loads(result), expected, name)
        print(result.decode("utf-8"), end="", flush=True)
    print("doc_03.json: 0 B", flush=True)
    source_view(root / "input/doc_01.pdf", records, "termin", 2,
                "wiersz_terminu", "Termin: 3 grudnia 2026")
    regression, rows, regression_time = cli(args, work / "input", work / "regresja", configuration)
    observed = check_outputs(regression, rows, CLASS_BY_FILE)
    defaults = work / "domyslne/output"
    expected = {name: digest(defaults / name) for name in CLASS_BY_FILE}
    verify(observed, expected, "SHA-256 regresji syntetycznej")
    count = len(expected)
    print(f"Regresja syntetyczna: {count}/{count} zgodnych SHA-256.")
    return {"cli_przed": before_time, "cli_zawiadomienia": elapsed, "cli_regresja": regression_time}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(path.read_bytes())


def stage_files(work, stage):
    files = {}
    for pattern in STAGE_FILES[stage]:
        paths = sorted(work.glob(pattern))
        if not paths:
            raise ValueError(f"Brak plików etapu {stage}: {pattern}")
        files.update({path.relative_to(work).as_posix(): digest(path) for path in paths})
    return files


def checked_stage(work, stage, identity):
    result = read_json(work / f"czasy-{stage}.json")
    verify(result["rewizja"], identity, f"Tożsamość etapu {stage}")
    verify(result["pliki"], stage_files(work, stage), f"Pliki etapu {stage}")
    return result


def quality_report(path, sha):
    report = read_json(path)
    verify(report["sha"], sha, "SHA pomiaru jakości")
    if report["zbior"] not in QUALITY_CORPORA:
        raise ValueError("Zbiór pomiaru jakości musi być rozwojowy albo niezalezny")
    manifest = report["sha256_manifestu"]
    if not re.fullmatch(r"[0-9a-f]{64}", manifest):
        raise ValueError("Niepoprawny SHA-256 manifestu pomiaru")
    counts = {key: report[key] for key in ("liczba_pdf", "tp", "fp", "fn")}
    if any(type(value) is not int or value < 0 for value in counts.values()) or not counts["liczba_pdf"]:
        raise ValueError("Niepoprawne liczniki pomiaru jakości")
    status = {key: report[key] for key in ("valid_run", "valid_contract")}
    if any(type(value) is not bool for value in status.values()):
        raise ValueError("Niepoprawny status pomiaru jakości")
    sample = 2 * counts["tp"] + counts["fp"] + counts["fn"]
    if not sample:
        raise ValueError("Brak punktowanych pól w pomiarze jakości")
    return {"sha": sha, "zbior": report["zbior"], "sha256_manifestu": manifest,
            **counts, **status, "micro_f1": 2 * counts["tp"] / sample}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path, help="repozytorium z kodem")
    parser.add_argument("work", type=Path, help="katalog przebiegu")
    parser.add_argument("etap", choices=["calosc", *STAGE_FILES])
    parser.add_argument("--sha", required=True, help="pełny SHA oczekiwanej rewizji")
    parser.add_argument("--image", help="wcześniej zbudowany obraz Docker z etykietą rewizji")
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--jakosc", type=Path, help="zatwierdzony pomiar koordynatora dla tego SHA")
    args = parser.parse_args()
    args.repo, args.work = args.repo.resolve(), args.work.resolve()
    verify(Path(__file__).resolve(), args.repo / "delivery/final/proba.py", "Ścieżka skryptu")
    verify(git(args.repo, "rev-parse", "HEAD"), args.sha, "SHA kodu")
    verify(git(args.repo, "status", "--porcelain"), "", "Stan checkoutu")
    if args.jakosc and args.etap not in ("calosc", "klasa"):
        parser.error("--jakosc wymaga etapu calosc albo klasa")
    quality = quality_report(args.jakosc, args.sha) if args.jakosc else None
    identity = {"sha": args.sha, "tryb": "natywny"}
    if args.image:
        inspect = json.loads(invoke([args.docker, "image", "inspect", args.image],
                                    args.repo, capture=True))[0]
        verify(inspect["Config"]["Labels"]["org.opencontainers.image.revision"], args.sha, "SHA obrazu")
        args.image = inspect["Id"]
        identity.update({"tryb": "Docker --network none", "image_id": args.image})
    os.environ["OMP_THREAD_LIMIT"] = "1"
    steps = {"przygotuj": prepare, "przelew": transfer, "klasa": extension}
    selected = steps if args.etap == "calosc" else [args.etap]
    for name in selected:
        previous = {}
        for stage in steps:
            if stage == name:
                break
            previous[stage] = checked_stage(args.work, stage, identity)
        started = perf_counter()
        elapsed = steps[name](args) or {}
        elapsed[name] = perf_counter() - started
        timings = {key: round(value, 3) for key, value in elapsed.items()}
        stage_record = {"rewizja": identity, "czasy_s": timings, "pliki": stage_files(args.work, name)}
        write_json(args.work / f"czasy-{name}.json", stage_record)
        if name == "klasa":
            write_json(args.work / "potwierdzenie.json", {
                "rewizja": identity, "etapy": {**previous, name: stage_record}, "jakosc": quality,
            })


if __name__ == "__main__":
    main()
