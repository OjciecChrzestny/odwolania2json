"""Buduje prezentację i zapis ekranów z rzeczywistej próby na syntetykach."""
import argparse
import json
from pathlib import Path

import pypdfium2
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from proba import CLASS_BY_FILE, STAGE_FILES, checked_stage, digest, git, read_json, verify, write_json

W, H = 960, 540
PAPER = "#F6F4EC"
INK = "#152E29"
MUTED = "#485B55"
GREEN = "#0B6254"
RULE = "#C7D0C7"
WHITE = "#FFFFFF"
SCREEN = "#142D28"
MINT = "#B3EBD5"
RUST = "#843A24"
UZP = "https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/de135d20811caf630f3e94dc655ba5eebd9a6710/README.md"


def text(pdf, x, y, value, size=23, font="Lato", ink=INK):
    pdf.setFont(font, size)
    pdf.setFillColor(HexColor(ink))
    pdf.drawString(x, H - y, value)


def block(pdf, x, y, lines, size=21, space=31, font="Lato", ink=MUTED):
    for i, line in enumerate(lines):
        text(pdf, x, y + i * space, line, size, font, ink)


def box(pdf, x, y, width, height, fill):
    pdf.setFillColor(HexColor(fill))
    pdf.rect(x, H - y - height, width, height, stroke=0, fill=1)


def line(pdf, x1, x2, y):
    pdf.setStrokeColor(HexColor(RULE))
    pdf.line(x1, H - y, x2, H - y)


def start(pdf, label, receipt, backup=False):
    box(pdf, 0, 0, W, H, PAPER)
    text(pdf, 52, 53, label, 14, "Lato Bold", GREEN)
    line(pdf, 52, 908, 68)
    prefix = "ZAPIS PRÓBY · SYNTETYKI" if backup else "Rewizja próby"
    text(pdf, 54, 524, f"{prefix}  /  {receipt['rewizja']['sha']}", 12, ink=MUTED)


def title(pdf, value):
    text(pdf, 52, 130, value, 43, "Lato Bold")


def link(pdf, x, y, label, url):
    text(pdf, x, y, label, 15, "Lato Bold", GREEN)
    width = pdfmetrics.stringWidth(label, "Lato Bold", 15)
    pdf.linkURL(url, (x, H - y - 3, x + width, H - y + 15), relative=0)


def terminal(pdf, x, y, width, height, label, content, size=14, leading=21):
    box(pdf, x, y, width, height, SCREEN)
    text(pdf, x + 20, y + 32, label, 14, "Lato Bold", MINT)
    lines = content.strip().splitlines()
    for line_text in lines:
        if pdfmetrics.stringWidth(line_text, "Mono", size) > width - 40:
            raise ValueError(f"Wiersz za szeroki na ekranie {label}: {line_text}")
    block(pdf, x + 20, y + 65, lines, size, leading, "Mono", WHITE)


def pdf_page(pdf, file, page, x, y, width, source_height, source_width=595):
    """Wyświetla fragment rzeczywistej strony od góry do końca istotnej treści."""
    with pypdfium2.PdfDocument(file) as source:
        sheet = source[page - 1]
        scale = 1.5
        bitmap = sheet.render(scale=scale)
        cropped = bitmap.to_pil().convert("RGB").crop((0, 0, int(source_width * scale), int(source_height * scale)))
        height = width * cropped.height / cropped.width
        box(pdf, x - 1, y - 1, width + 2, height + 2, RULE)
        pdf.drawImage(ImageReader(cropped), x, H - y - height, width, height)
        bitmap.close()
        sheet.close()
        return height


def evidence(diagnostics, output, field):
    rows = json.loads(diagnostics.read_bytes())["documents"]
    row = next(row for row in rows if row["output"] == output)
    return row["fields"][field]


def present(path, work, receipt):
    pdf = Canvas(str(path), pagesize=(W, H), pageCompression=1, invariant=1)
    pdf.setTitle("Odwołania2JSON — pokaz dla UZP")
    transfer = work / "input/doc_01.pdf"
    notice = work / "rozszerzenie/input/doc_01.pdf"

    start(pdf, "HackNation 2026 / Urząd Zamówień Publicznych", receipt)
    text(pdf, 52, 164, "Odwołania2JSON", 72, "Lato Bold")
    text(pdf, 55, 213, "Dokumenty KIO jako ustrukturyzowane dane", 30)
    text(pdf, 55, 264, "Odwołanie, pełnomocnictwo i potwierdzenie przelewu", 21, ink=MUTED)
    terminal(pdf, 55, 294, 402, 83, "POLECENIE", "python -m odwolania2json", 17)
    line(pdf, 55, 908, 418)
    for x, head, detail in [
        (55, "PDF", "folder input/"),
        (190, "Odczyt", "tekst lub OCR"),
        (366, "Klasyfikacja", "sygnały i próg"),
        (550, "Ekstrakcja", "reguły i schemat"),
        (731, "Wynik", "JSON i diagnostyka"),
    ]:
        text(pdf, x, 454, head, 23, "Lato Bold", GREEN)
        text(pdf, x, 480, detail, 18, ink=MUTED)
    pdf.showPage()

    start(pdf, "0:35–1:20 / Źródło pola", receipt)
    title(pdf, "Kwota z pierwszej strony PDF-u")
    pdf_page(pdf, transfer, 1, 54, 164, 430, 392)
    text(pdf, 56, 468, "Fikcyjne potwierdzenie przelewu", 17, ink=MUTED)
    text(pdf, 524, 203, "123.45", 73, "Lato Bold", GREEN)
    text(pdf, 528, 238, "kwota w wynikowym JSON-ie", 20, ink=MUTED)
    line(pdf, 528, 902, 274)
    block(pdf, 528, 313, ["Strona 1", "Reguła kwota_operacji"], 25, 36, "Lato Bold", INK)
    block(pdf, 528, 414, ["Diagnostyka prowadzi do strony", "z wierszem „Kwota: 123,45 PLN”."], 20, 28)
    pdf.showPage()

    review_page(pdf, work, receipt)

    start(pdf, "0:35–1:20 / Jakość ekstrakcji", receipt)
    title(pdf, "Ścisłe mikro-F1 na polach")
    quality = receipt["jakosc"]
    if quality is None:
        text(pdf, 55, 211, "Pomiar tej rewizji czeka na odbiór", 31, "Lato Bold")
        block(pdf, 55, 273, ["Pokaz używa wyłącznie syntetycznych PDF-ów.",
                            "Znamy wyniki prób funkcjonalnych na tych przykładach.",
                            "Wynik na zbiorze jury pozostaje nieznany."], 23, 41)
    else:
        fraction = f"{100 * quality['micro_f1']:.2f}".replace(".", ",")
        valid = quality["valid_run"] and quality["valid_contract"]
        corpus = {"rozwojowy": "rozwojowy", "niezalezny": "niezależny"}[quality["zbior"]]
        text(pdf, 55, 235, f"{fraction}%", 68, "Lato Bold", GREEN if valid else RUST)
        text(pdf, 55, 280, f"Zbiór {corpus} · PDF-y: {quality['liczba_pdf']}", 27, "Lato Bold")
        text(pdf, 55, 324, f"TP {quality['tp']}   FP {quality['fp']}   FN {quality['fn']}", 23)
        status = f"valid_run={str(quality['valid_run']).lower()}   " \
                 f"valid_contract={str(quality['valid_contract']).lower()}"
        text(pdf, 55, 376, status, 20, "Mono")
        if not valid:
            text(pdf, 55, 421, "Pomiar diagnostyczny. Warunek ważności niezaliczony.", 23, "Lato Bold", RUST)
        text(pdf, 55, 486, "Wynik na zbiorze jury pozostaje nieznany.", 19, ink=MUTED)
    pdf.showPage()

    start(pdf, "1:20–2:00 / Dodanie klasy", receipt)
    title(pdf, "Zawiadomienie w jednym pliku JSON")
    text(pdf, 54, 166, "zawiadomienie.json", 23, "Mono", GREEN)
    text(pdf, 54, 198, "Sygnały klasy, próg, schemat i reguły pól", 19, ink=MUTED)
    pdf_page(pdf, notice, 2, 54, 232, 403, 199, 430)
    text(pdf, 54, 445, "Strona 2 · reguła wiersz_terminu", 21, "Lato Bold")
    terminal(pdf, 494, 232, 412, 143, "DOC_01.JSON",
             (work / "rozszerzenie/demo/output/doc_01.json").read_text(encoding="utf-8"))
    text(pdf, 494, 414, "Obce pismo  0 B", 24, "Lato Bold", GREEN)
    count = len(CLASS_BY_FILE)
    text(pdf, 494, 448, f"Regresja syntetyczna  {count}/{count}", 23, "Lato Bold")
    text(pdf, 494, 476, "Zgodne sumy SHA-256 przed i po zmianie", 16, ink=MUTED)
    pdf.showPage()

    start(pdf, "Aneks / Implementacja", receipt)
    title(pdf, "Ekstrakcja lokalna, bez API")
    block(pdf, 55, 197, ["pypdf odczytuje warstwę tekstową ze wszystkich stron.",
                        "OCR skanów używa pypdfium2 / PDFium i tesserocr / Tesseract.",
                        "OCR domyślnie obejmuje najwyżej sześć różnych stron.",
                        "Docker Compose uruchamia ten sam interfejs CLI."],
          23, 47, "Lato", INK)
    link(pdf, 55, 436, "Wymagania UZP", UZP)
    link(pdf, 55, 469, "Licencja pypdf", "https://pypi.org/project/pypdf/6.21.4/")
    link(pdf, 250, 469, "Licencje PDFium i pypdfium2", "https://github.com/pypdfium2-team/pypdfium2#license")
    link(pdf, 515, 469, "Licencja Tesseract", "https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE")
    text(pdf, 55, 503, "Wykaz komponentów i przypięte wersje znajdują się w instrukcji jurora.", 16, ink=MUTED)
    pdf.save()


def review_page(pdf, work, receipt, backup=False):
    start(pdf, "Ekran 3 / Ręczna kontrola" if backup else "0:35–1:20 / Ręczna kontrola",
          receipt, backup=backup)
    title(pdf, "Przelew bez numeru transakcji")
    pdf_page(pdf, work / "input/doc_05.pdf", 1, 54, 159, 427, 416)
    result = read_json(work / "domyslne/output/doc_05.json")["przelew_bankowy"]
    terminal(pdf, 510, 159, 396, 109, "FRAGMENT DOC_05.JSON",
             json.dumps({"numer_transakcji": result["numer_transakcji"]}, indent=2), 14, 16)
    block(pdf, 510, 326, ["Program zwrócił puste pole.",
                          "Prezenter sprawdza stronę 1.",
                          "Brak numeru w źródle."], 23, 38, "Lato", INK)
    text(pdf, 510, 465, "Przykład ręcznej weryfikacji", 19, "Lato Bold", GREEN)
    pdf.showPage()


def backup(path, work, receipt):
    pdf = Canvas(str(path), pagesize=(W, H), pageCompression=1, invariant=1)
    pdf.setTitle("Odwołania2JSON — ekrany rezerwowe")
    transfer = work / "domyslne"
    extension = work / "rozszerzenie"

    start(pdf, "Ekran 1 / PDF i wynik CLI", receipt, backup=True)
    title(pdf, "Potwierdzenie przelewu")
    pdf_page(pdf, work / "input/doc_01.pdf", 1, 54, 159, 394, 440)
    terminal(pdf, 464, 159, 442, 266, "OUTPUT/DOC_01.JSON",
             (transfer / "output/doc_01.json").read_text(encoding="utf-8"), 13, 21)
    text(pdf, 54, 475, "doc_02.json  0 B  ·  Wezwanie do zapłaty", 22, "Lato Bold", GREEN)
    pdf.showPage()

    start(pdf, "Ekran 2 / Źródło pola", receipt, backup=True)
    title(pdf, "Kwota 123.45 w JSON-ie")
    pdf_page(pdf, work / "input/doc_01.pdf", 1, 54, 159, 440, 355)
    field = "przelew_bankowy.kwota"
    row = evidence(transfer / "diagnostics/last-run.json", "doc_01.json", field)
    snippet = json.dumps({field: {"page": row["page"], "rule": row["rule"]}},
                         ensure_ascii=False, indent=2)
    terminal(pdf, 524, 159, 382, 185, "DIAGNOSTYKA / FIELDS", snippet, 15, 22)
    text(pdf, 524, 395, "„Kwota: 123,45 PLN”", 24, "Lato Bold", GREEN)
    text(pdf, 524, 427, "Fikcyjny PDF · strona 1", 18, ink=MUTED)
    pdf.showPage()

    review_page(pdf, work, receipt, backup=True)

    start(pdf, "Ekran 4 / Nowa klasa", receipt, backup=True)
    title(pdf, "Termin z drugiej strony")
    text(pdf, 54, 169, "demo/rozszerzalnosc/zawiadomienie.json", 19, "Mono", GREEN)
    pdf_page(pdf, extension / "input/doc_01.pdf", 2, 54, 199, 409, 218, 430)
    notice = (extension / "demo/output/doc_01.json").read_text(encoding="utf-8")
    terminal(pdf, 494, 198, 412, 151, "OUTPUT/DOC_01.JSON", notice, 15, 22)
    row = evidence(extension / "demo/diagnostics/last-run.json", "doc_01.json", "termin")
    text(pdf, 54, 446, f"Strona {row['page']} · {row['rule']}", 20, "Lato Bold")
    text(pdf, 494, 391, "Obce pismo  0 B", 22, "Lato Bold", GREEN)
    text(pdf, 494, 430, "Regresja na tych samych syntetykach", 20, "Lato Bold")
    count = len(CLASS_BY_FILE)
    text(pdf, 494, 460, f"{count}/{count} zgodnych SHA-256", 18, ink=MUTED)
    pdf.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path, help="syntetyczny przebieg proba.py calosc")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    receipt_path = args.work / "potwierdzenie.json"
    receipt = read_json(receipt_path)
    identity = receipt["rewizja"]
    verify(identity["sha"], git(repo, "rev-parse", "HEAD"), "SHA materiałów")
    verify(git(repo, "status", "--porcelain"), "", "Stan checkoutu")
    for stage in STAGE_FILES:
        verify(receipt["etapy"][stage], checked_stage(args.work, stage, identity), f"Zapis etapu {stage}")
    if receipt["jakosc"] is not None:
        verify(receipt["jakosc"]["sha"], identity["sha"], "SHA pomiaru jakości")
    fonts = Path("/usr/share/fonts/truetype")
    for name, file in [
        ("Lato", "lato/Lato-Regular.ttf"), ("Lato Bold", "lato/Lato-Bold.ttf"),
        ("Mono", "dejavu/DejaVuSansMono.ttf"),
    ]:
        pdfmetrics.registerFont(TTFont(name, str(fonts / file)))
    args.output.mkdir()
    presentation = args.output / "prezentacja.pdf"
    saved = args.output / "ekrany-rezerwowe.pdf"
    present(presentation, args.work, receipt)
    backup(saved, args.work, receipt)
    write_json(args.output / "materialy.json", {
        "rewizja": identity,
        "sha256_potwierdzenia": digest(receipt_path),
        "pliki": {path.name: digest(path) for path in (presentation, saved)},
    })


if __name__ == "__main__":
    main()
