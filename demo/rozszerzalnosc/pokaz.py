"""Przygotowuje pokaz i odczytuje strony wskazane przez diagnostykę."""
import argparse
import json
import shutil
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def write_pdf(path, pages):
    """Minimalny PDF z warstwą tekstową, tak jak w testach wariantu A."""
    pdf = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    for number, lines in enumerate(pages, 1):
        page = pdf.add_blank_page(width=595, height=842)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        body = " Tj T* ".join(f"({line})" for line in lines[1:])
        content = DecodedStreamObject()
        content.set_data((
            "BT /F1 10 Tf 64 780 Td (FIKCYJNY DOKUMENT | DEMO UZP) Tj "
            f"/F1 24 Tf 0 -54 Td ({lines[0]}) Tj "
            f"/F1 13 Tf 22 TL 0 -43 Td {body} Tj ET "
            f"BT /F1 10 Tf 64 60 Td (Strona {number} z {len(pages)}) Tj ET"
        ).encode("ascii"))
        page.replace_contents(content)
    pdf.write(path)


def prepare(work):
    """Tworzy wyłącznie nowy katalog roboczy."""
    work.mkdir()
    input_dir = work / "input"
    input_dir.mkdir()
    shutil.copytree(ROOT / "odwolania2json/classes", work / "klasy")
    write_pdf(input_dir / "doc_01.pdf", [
        ("ZAWIADOMIENIE", "Sygnatura: KIO-DEMO/17/26", "Szczegoly posiedzenia znajduja sie na stronie 2."),
        ("POSIEDZENIE", "Termin: 3 grudnia 2026", "Posiedzenie odbedzie sie zdalnie."),
    ])
    write_pdf(input_dir / "doc_02.pdf", [
        ("ZAWIADOMIENIE", "Sygnatura akt: KIO-DEMO/42/27", "Termin posiedzenia: 18.01.2027"),
    ])
    write_pdf(input_dir / "doc_03.pdf", [
        ("KOMUNIKAT ORGANIZACYJNY", "Zawiadomienie zostanie wyslane osobno.",
         "Termin: 9 grudnia 2026", "Sygnatura: ORG-DEMO/4/26"),
    ])


def show_source(pdf, diagnostics, output):
    document = next(
        (row for row in json.loads(diagnostics.read_bytes())["documents"] if row["output"] == output),
        None,
    )
    if document is None:
        raise ValueError(f"Brak wpisu diagnostycznego dla {output}")
    if not document["fields"]:
        print(f"{output} | status {document['status']} | brak źródeł pól")
        return
    reader = PdfReader(pdf)
    fields_by_page = {}
    for field, evidence in document["fields"].items():
        fields_by_page.setdefault(evidence["page"], []).append(f"{field} → {evidence['rule']}")
    for page, rules in sorted(fields_by_page.items()):
        print(f"{pdf.name} | strona {page} | {', '.join(rules)}")
        print(reader.pages[page - 1].extract_text().strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("przygotuj")
    generate.add_argument("work", type=Path)
    source = commands.add_parser("zrodlo")
    source.add_argument("pdf", type=Path)
    source.add_argument("diagnostics", type=Path)
    source.add_argument("--output", help="neutralna ścieżka JSON z diagnostyki, jeśli plik jest w podkatalogu")
    args = parser.parse_args()
    if args.command == "przygotuj":
        prepare(args.work)
    else:
        show_source(args.pdf, args.diagnostics, args.output or args.pdf.with_suffix(".json").name)


if __name__ == "__main__":
    main()
