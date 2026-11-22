"""A later receipt must establish the transfer from its own physical page."""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from odwolania2json.bank_scan import ScanView
from odwolania2json.extract import extract, read_pdf
from odwolania2json.model import Document, load_classes
from odwolania2json.ocr import LocalOCR


COVER = "Strona tytulowa\nArkusz 1 z 2"
PAYER = "02112233445566778899001122"
RECIPIENT = "77499988887777666655554433"
RECEIPT = (
    "Potwierdzenie wykonania przelewu\n"
    "Kwota: 47,25 PLN\n"
    "Data operacji: 2026-05-19\n"
    "Status: Zrealizowany\n"
    f"Na rachunek: {RECIPIENT}\n"
    f"Z rachunku: {PAYER}\n"
)
ATTORNEY = (
    "PEŁNOMOCNICTWO\nMocodawca: Fikcyjna Północ sp. z o.o.\n"
    "Udziela pełnomocnictwa Ninie Zorzy do reprezentowania przed Krajową Izbą Odwoławczą.\n"
)


def write_pdf(path, *texts, painted_cover=False):
    pdf = PdfWriter()
    for index, text in enumerate(texts):
        page = pdf.add_blank_page(width=595, height=842)
        if not text:
            continue
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        content = DecodedStreamObject()
        commands = ["BT /F1 12 Tf 42 700 Td 18 TL"]
        commands.extend(f"({line}) Tj T*" for line in text.splitlines())
        commands.append("ET")
        if painted_cover and not index:
            commands.append("20 100 500 550 re f")
        content.set_data(" ".join(commands).encode("ascii"))
        page[NameObject("/Contents")] = pdf._add_object(content)
    pdf.write(path)


class TransferCoverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.pdf = Path(directory.name) / "receipt.pdf"

    def assert_receipt(self, document):
        data, diagnostic = extract(document, self.classes)
        self.assertEqual(diagnostic["class"], "przelew")
        payment = data["przelew_bankowy"]
        self.assertEqual((payment["z_rachunku"], payment["na_rachunek"]), (PAYER, RECIPIENT))
        self.assertEqual((payment["kwota"], payment["data_operacji"]), (47.25, "2026-05-19"))
        self.assertEqual({signal["page"] for signal in diagnostic["signals"]}, {2})
        self.assertEqual({field["page"] for field in diagnostic["fields"].values()}, {2})

    def test_native_cover_reads_only_the_unreadable_second_page(self):
        write_pdf(self.pdf, COVER, "")
        ocr = Mock(return_value=[(1, RECEIPT)])
        document, pages = read_pdf(self.pdf, ocr, classes=self.classes)
        ocr.assert_called_once_with(self.pdf, 2, start=1)
        self.assertEqual(pages, [2])
        self.assert_receipt(document)

    def test_two_native_pages_need_no_ocr_or_guessing_from_order(self):
        write_pdf(self.pdf, COVER, RECEIPT)
        ocr = Mock(side_effect=AssertionError("unexpected OCR"))
        document, pages = read_pdf(self.pdf, ocr, classes=self.classes)
        self.assertEqual(pages, [])
        self.assert_receipt(document)
        ocr.assert_not_called()

    def test_metadata_cover_accepts_distinct_layouts_without_treating_an_attachment_as_primary(self):
        receipts = (
            ("Metryka skanu\nIdentyfikator skanu: A17\nFormat pliku: PDF/A\nStr. 1/2", RECEIPT),
            ("01/02\nOznaczenie digitalizacji\nData digitalizacji: 2026-05-20", RECEIPT),
            ("Numer pliku: F-87\nStrona 1 z 2\nWersja pliku: V2", RECEIPT),
        )
        rejected = (
            ("Strona archiwalna\nZalacznik: potwierdzenie przelewu\nStr. 1/2", RECEIPT),
            ("Metryka skanu\nKwota: 79,99 PLN\nArkusz 1 z 2", RECEIPT),
            ("Strona separujaca\nUwagi: Prosze o zwrot towaru\nStr. 1/2", RECEIPT),
            ("Metryka skanu\nStrona 1 z 2", RECEIPT.replace("Zrealizowany", "Do realizacji")),
            ("01/02", RECEIPT),
        )
        for opening, receipt in (*receipts, *rejected):
            with self.subTest(opening=opening, receipt=receipt):
                write_pdf(self.pdf, opening, receipt)
                document, _ = read_pdf(self.pdf, classes=self.classes)
                if (opening, receipt) in receipts:
                    self.assert_receipt(document)
                else:
                    self.assertIsNone(extract(document, self.classes)[0])

    def test_empty_ocr_text_requires_a_visually_verified_opening(self):
        write_pdf(self.pdf, "", "")
        ocr = LocalOCR(None, None, self.pdf.parent)
        for physically_blank in (False, True):
            with (self.subTest(physically_blank=physically_blank),
                  patch.object(LocalOCR, "oriented_pages", autospec=True,
                               return_value=[(0, ""), (1, RECEIPT)]) as read,
                  patch.object(LocalOCR, "blank_opening", autospec=True,
                               return_value=physically_blank) as verify):
                document, pages = read_pdf(self.pdf, ocr, classes=self.classes)
                read.assert_called_once_with(ocr, self.pdf, 2)
                verify.assert_called_once_with(ocr, self.pdf)
                self.assertEqual(pages, [2])
                if physically_blank:
                    self.assert_receipt(document)
                else:
                    self.assertIsNone(extract(document, self.classes)[0])

    def test_other_openings_and_limits_do_not_trigger_ocr(self):
        cases = (
            ("Karta sprawy\nZalacznik dokumentuje wplate", False, 2, None),
            (COVER, True, 2, None),
            (COVER, False, 0, None),
            (COVER, False, 2, 2),
        )
        for title, painted, budget, limit in cases:
            with self.subTest(title=title, painted=painted, budget=budget, limit=limit):
                write_pdf(self.pdf, title, "", *(("",) if limit else ()), painted_cover=painted)
                ocr = Mock(side_effect=AssertionError("unexpected OCR"))
                document, pages = read_pdf(self.pdf, ocr, max_pages=limit, classes=self.classes,
                                           ocr_page_budget=budget)
                self.assertEqual(pages, [])
                ocr.assert_not_called()
                self.assertIsNone(extract(document, self.classes)[0])

    def test_nonexecuted_example_card_and_split_signals_stay_negative(self):
        cases = (
            (COVER, RECEIPT.replace("Zrealizowany", "Oczekuje na realizacje")),
            (COVER, RECEIPT + "Status: Anulowany przez bank\n"),
            (COVER, "Instrukcja dla użytkownika\nPoniżej przykład\n" + RECEIPT),
            (COVER, RECEIPT + "Typ operacji: Płatność kartą\n"),
            (COVER, RECEIPT.replace("2026-05-19", "2026-02-31")),
            (COVER, RECEIPT + "Kwota: 95,26 PLN\n"),
            (COVER, RECEIPT + "Data operacji: 2026-05-20\n"),
            (COVER, RECEIPT + RECEIPT),
            (COVER, RECEIPT.replace(f"Na rachunek: {RECIPIENT}\n", "")),
            ("Okładka\nStatus: Zrealizowany", RECEIPT.replace("Status: Zrealizowany\n", "")),
            (COVER, RECEIPT.replace("Status: Zrealizowany\n", "")),
            (COVER, RECEIPT.replace("Potwierdzenie wykonania przelewu", "Polecenie przelewu")),
        )
        for opening, later in cases:
            with self.subTest(opening=opening, later=later):
                document = replace(Document.from_pages([opening, later]), transfer_cover_verified=True)
                self.assertIsNone(extract(document, self.classes)[0])

    def test_same_role_conflicts_with_named_parties_abstain_from_only_that_account(self):
        distinct = "55" + "000000000000000000000011"
        body = "000000000000000000000011"
        valid = f"{98 - int(body + '252100') % 97:02d}{body}"
        for extra_account in (RECIPIENT, valid, distinct):
            with self.subTest(extra_account=extra_account):
                initial = RECEIPT.replace(f"Na rachunek: {RECIPIENT}", f"Odbiorca: Alfa\nNa rachunek: {RECIPIENT}")
                later = initial + f"Beneficjent: Beta\nRachunek odbiorcy: {extra_account}\n"
                write_pdf(self.pdf, "Metryka skanu\nStr. 1/2", later)
                document, _ = read_pdf(self.pdf, classes=self.classes)
                data, diagnostic = extract(document, self.classes)
                self.assertEqual(diagnostic["class"], "przelew")
                bank = data["przelew_bankowy"]
                self.assertEqual(bank["z_rachunku"], PAYER)
                self.assertEqual(bank["na_rachunek"], RECIPIENT if extra_account == RECIPIENT else None)
                self.assertEqual("przelew_bankowy.na_rachunek" in diagnostic["fields"], extra_account == RECIPIENT)

    def test_a_classified_document_keeps_its_own_class_with_an_attachment(self):
        document = replace(Document.from_pages([ATTORNEY, RECEIPT]), transfer_cover_verified=True)
        data, diagnostics = extract(document, self.classes)
        self.assertEqual(diagnostics["class"], "pelnomocnictwo")
        self.assertNotIn("przelew_bankowy", data)

    def test_optional_bank_ocr_is_also_restricted_to_the_receipt_page(self):
        foreign = ScanView(1, "Kwota: 12000,00 PLN", ("Kwota: 12000,00 PLN",))
        scan = Mock(return_value=[foreign])
        document = replace(Document.from_pages([COVER, RECEIPT]), bank_scan=scan,
                           transfer_cover_verified=True)
        self.assert_receipt(document)
        scan.assert_called_once()


if __name__ == "__main__":
    unittest.main()
