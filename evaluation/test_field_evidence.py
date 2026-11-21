"""Reproduce field citations on synthetic PDFs, including misleading numbers."""
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

from odwolania2json.extract import extract, read_pdf
from odwolania2json.field_evidence import with_field_sources
from odwolania2json.model import Document, Extraction, load_classes

AMOUNT = "przelew_bankowy.kwota"
AMOUNT_PATH = tuple(AMOUNT.split("."))
ACTUAL = "1 123,45"
COVER = "POTWIERDZENIE PRZELEWU\nNumer transakcji: REF2026001\nProwizja: 1 123,45 PLN"
DETAIL = "\n".join((
    "Saldo: 1 123,55 PLN",
    f"Prowizja: {ACTUAL} PLN",
    f"Kwota: {ACTUAL} PLN",
    "Data operacji: 01.02.2026",
    "Opis: Test podstawy pola",
    "Kierunek: Przelew wychodzacy",
    "Dane kontrahenta",
    "Numer rachunku 12998877665544998877665544",
))


def pdf_dict(**entries):
    return DictionaryObject({NameObject("/" + key): value for key, value in entries.items()})


def content(page, commands):
    stream = DecodedStreamObject()
    stream.set_data(commands.encode("ascii"))
    page.replace_contents(stream)


def write_text_pdf(path, *pages):
    pdf = PdfWriter()
    for text in pages:
        page = pdf.add_blank_page(width=600, height=800)
        if text:
            font = pdf_dict(Type=NameObject("/Font"), Subtype=NameObject("/Type1"),
                            BaseFont=NameObject("/Helvetica"))
            page[NameObject("/Resources")] = pdf_dict(Font=pdf_dict(F1=font))
            lines = " Tj T* ".join(f"({line})" for line in text.splitlines())
            content(page, f"BT /F1 17 Tf 27 TL 40 750 Td {lines} Tj ET")
    pdf.write(path)


def write_image_pdf(path, source):
    """Rasterize one synthetic page for the opt-in acceptance run with local OCR."""
    from pypdfium2 import PdfDocument

    image = DecodedStreamObject()
    with closing(PdfDocument(source)) as pdf, closing(pdf[0]) as page:
        with closing(page.render(scale=2, grayscale=True)) as bitmap:
            pixels = bytes(bitmap.buffer)
            width, height = bitmap.width, bitmap.height
            image.set_data(b"".join(
                pixels[start:start + width] for start in range(0, len(pixels), bitmap.stride)
            ))
    image = image.flate_encode()
    image.update(pdf_dict(Type=NameObject("/XObject"), Subtype=NameObject("/Image"),
                          Width=NumberObject(width), Height=NumberObject(height),
                          ColorSpace=NameObject("/DeviceGray"), BitsPerComponent=NumberObject(8)))
    output = PdfWriter()
    page = output.add_blank_page(width=600, height=800)
    page[NameObject("/Resources")] = pdf_dict(XObject=pdf_dict(Im1=output._add_object(image)))
    content(page, "q 600 0 0 800 0 0 cm /Im1 Do Q")
    output.write(path)


class FieldEvidenceTest(TestCase):
    def setUp(self):
        root = TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.pdf = Path(root.name) / "fixture.pdf"
        self.classes = load_classes()

    def check_amount(self, document, ocr_pages, *, page, source):
        data, record = extract(document, self.classes)
        fields = with_field_sources(record["fields"], ocr_pages=ocr_pages)
        self.assertEqual(data["przelew_bankowy"]["kwota"], 1123.45)
        read_page = document.text.split("\n\f\n")[page - 1]
        start = read_page.index("Kwota: " + ACTUAL) + len("Kwota: ")
        self.assertEqual(fields[AMOUNT], {
            "page": page, "rule": "kwota_operacji", "source": source,
            "precision": "snippet", "snippet": ACTUAL, "context": "Kwota: " + ACTUAL,
            "span": {"start": start, "end": start + len(ACTUAL)},
        })
        return fields

    def test_native_pdf_points_to_selected_field_even_when_value_repeats(self):
        write_text_pdf(self.pdf, COVER, DETAIL)
        doc, ocr_pages = read_pdf(self.pdf, classes=self.classes)
        fields = self.check_amount(doc, ocr_pages, page=2, source="text")
        self.assertEqual(fields["przelew_bankowy.na_rachunek"], {
            "page": 2, "rule": "nrb_mod97_i_rola_na_stronie", "source": "text", "precision": "page",
        })

    def test_reader_ocr_text_has_ocr_source(self):
        write_text_pdf(self.pdf, "")

        def scan(path, limit):
            self.assertEqual((path, limit), (self.pdf, 1))
            return [(0, COVER + "\n" + DETAIL)]

        doc, ocr_pages = read_pdf(self.pdf, scan, classes=self.classes)
        self.check_amount(doc, ocr_pages, page=1, source="ocr")

    def test_legacy_offset_at_wrong_page_or_field_cannot_produce_quote(self):
        document = Document.from_pages([COVER, DETAIL])
        result = Extraction(document, {"przelew_bankowy": {"kwota": "number?"}})
        for offset in (
            0,
            document.starts[1][0],
            COVER.index(ACTUAL),
            document.starts[1][0] + DETAIL.index(ACTUAL),
        ):
            with self.subTest(offset=offset):
                result.put(AMOUNT_PATH, 1123.45, offset, "kwota_operacji")
                self.assertEqual(result.evidence[AMOUNT]["precision"], "page")
                self.assertNotIn("snippet", result.evidence[AMOUNT])

    def test_explicit_span_must_be_on_one_page_and_normalize_to_value(self):
        document = Document.from_pages(["123,50", ACTUAL])
        result = Extraction(document, {"przelew_bankowy": {"kwota": "number?"}})
        start = document.starts[1][0]
        for offset, end in ((0, 6), (0, start + len(ACTUAL))):
            with self.subTest(offset=offset, end=end):
                result.put(AMOUNT_PATH, 1123.45, offset, "nowa_reguła", span_end=end, operation="money")
                self.assertEqual(result.evidence[AMOUNT]["precision"], "page")
        result.put(AMOUNT_PATH, 1123.45, start, "nowa_reguła", span_end=start + len(ACTUAL),
                   operation="money", source="ocr")
        found = with_field_sources(result.evidence, ocr_pages=())[AMOUNT]
        self.assertEqual((found["page"], found["source"], found["snippet"]), (2, "ocr", ACTUAL))

    def test_ocr_recovery_with_technical_offset_has_only_page_precision(self):
        document = Document.from_pages([f"Kwota: {ACTUAL} PLN"])
        result = Extraction(document, {"przelew_bankowy": {"kwota": "number?"}})
        result.put(AMOUNT_PATH, 1123.45, 0, "ocr_wiersz_kwoty")
        self.assertEqual(result.evidence[AMOUNT], {
            "page": 1, "rule": "ocr_wiersz_kwoty", "source": "ocr", "precision": "page",
        })

    def test_invalid_offset_is_not_misattributed_to_last_page(self):
        document = Document.from_pages(["123,50", ACTUAL])
        result = Extraction(document, {"przelew_bankowy": {"kwota": "number?"}})
        result.put(AMOUNT_PATH, 1123.45, -1, "nowa_reguła")
        self.assertEqual(result.evidence[AMOUNT], {
            "page": None, "rule": "nowa_reguła", "source": None, "precision": "unavailable",
        })
