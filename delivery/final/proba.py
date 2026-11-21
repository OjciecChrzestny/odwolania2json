"""Próba jurora na świeżych syntetykach i publicznym CLI wybranej rewizji."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

BEFORE = "c01401cd7abdf82655b18188f68cb46652dc239e"
AFTER = "72337e2164f871fa3b1d6c63edde0381b7ed8b31"
CONFIG_PATH = "demo/rozszerzalnosc/zawiadomienie.json"
FONT = "/usr/share/fonts/truetype/lato/Lato-Regular.ttf"
AMOUNT_LINE = "Kwota: 123,45 PLN"
CLASS_BY_FILE = {
    "doc_01.json": "przelew",
    "doc_02.json": "negative",
    "doc_03.json": "odwolanie",
    "doc_04.json": "pelnomocnictwo",
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
    make_pdf(source / "doc_01.pdf", "Potwierdzenie przelewu", [
        "Data operacji: 21 listopada 2026",
        AMOUNT_LINE,
        "Z rachunku: " + TRANSFER["z_rachunku"],
        "Na rachunek: " + TRANSFER["na_rachunek"],
        "Tytuł: Wpis za odwołanie",
        "Numer transakcji: " + TRANSFER["numer_transakcji"],
    ])
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


def source_view(args, pdf, run, field, expected_page, expected_rule, expected_line):
    diagnostics = run / "diagnostics/last-run.json"
    evidence = next(row["fields"][field] for row in json.loads(diagnostics.read_bytes())["documents"]
                    if row["output"] == pdf.with_suffix(".json").name)
    verify(evidence, {"page": expected_page, "rule": expected_rule}, field)
    page_text = PdfReader(pdf).pages[expected_page - 1].extract_text()
    verify(expected_line in page_text.splitlines(), True, f"Tekst {pdf.name}")
    invoke([sys.executable, args.repo / "demo/rozszerzalnosc/pokaz.py", "zrodlo",
            pdf, diagnostics], args.repo)


def check_outputs(output, records, expected):
    verify({name: row["class"] for name, row in records.items()}, expected, "Klasy dokumentów")
    verify(sorted(path.name for path in output.iterdir()), sorted(expected), "Ścieżki JSON")
    for name, label in expected.items():
        negative = label == "negative"
        verify(records[name]["status"], "negative" if negative else "ok", name)
        verify((output / name).stat().st_size == 0, negative, name)
    return {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in expected}


def transfer(args):
    source, target = args.work / "input", args.work / "domyslne"
    output, records, elapsed = cli(args, source, target)
    check_outputs(output, records, CLASS_BY_FILE)
    verify(json.loads((output / "doc_01.json").read_bytes()), {"przelew_bankowy": TRANSFER}, "Przelew")
    print((output / "doc_01.json").read_text(encoding="utf-8"), end="", flush=True)
    print("doc_02.json: 0 B", flush=True)
    source_view(args, source / "doc_01.pdf", target, "przelew_bankowy.kwota", 1,
                "kwota_operacji", AMOUNT_LINE)
    return {"cli_domyslne": elapsed}


def extension(args):
    work, root = args.work, args.work / "rozszerzenie"
    configuration = root / "klasy"
    diff = git(args.repo, "diff", "--name-only", BEFORE, AFTER)
    verify(diff, CONFIG_PATH, "Diff dodania klasy")
    print(diff, flush=True)
    shutil.copyfile(args.repo / CONFIG_PATH, configuration / "zawiadomienie.json")
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
    source_view(args, root / "input/doc_01.pdf", target, "termin", 2,
                "wiersz_terminu", "Termin: 3 grudnia 2026")
    regression, rows, regression_time = cli(args, work / "input", work / "regresja", configuration)
    observed = check_outputs(regression, rows, CLASS_BY_FILE)
    defaults = work / "domyslne/output"
    expected = {name: hashlib.sha256((defaults / name).read_bytes()).hexdigest() for name in CLASS_BY_FILE}
    verify(observed, expected, "SHA-256 regresji syntetycznej")
    print("Regresja syntetyczna na tej rewizji: 4/4 zgodne SHA-256. Trzy klasy i negatyw.")
    return {"cli_zawiadomienia": elapsed, "cli_regresja": regression_time}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path, help="repozytorium z kodem")
    parser.add_argument("work", type=Path, help="katalog przebiegu")
    parser.add_argument("etap", choices=["calosc", "przygotuj", "przelew", "klasa"])
    parser.add_argument("--sha", required=True, help="pełny SHA oczekiwanej rewizji")
    parser.add_argument("--image", help="wcześniej zbudowany obraz Docker z etykietą rewizji")
    parser.add_argument("--docker", default="docker")
    args = parser.parse_args()
    args.repo, args.work = args.repo.resolve(), args.work.resolve()
    verify(git(args.repo, "rev-parse", "HEAD"), args.sha, "SHA kodu")
    verify(git(args.repo, "status", "--porcelain"), "", "Stan checkoutu")
    if args.image:
        label = invoke([args.docker, "image", "inspect", "--format",
                        '{{index .Config.Labels "org.opencontainers.image.revision"}}', args.image],
                       args.repo, capture=True)
        verify(label.strip(), args.sha, "SHA obrazu")
    steps = {"przygotuj": prepare, "przelew": transfer, "klasa": extension}
    timings = {"sha": args.sha, "tryb": "Docker --network none" if args.image else "natywny"}
    selected = steps if args.etap == "calosc" else [args.etap]
    for name in selected:
        started = perf_counter()
        cli_times = steps[name](args)
        timings[name] = round(perf_counter() - started, 3)
        timings.update({key: round(value, 3) for key, value in (cli_times or {}).items()})
    (args.work / f"czasy-{args.etap}.json").write_text(
        json.dumps(timings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )


if __name__ == "__main__":
    main()
