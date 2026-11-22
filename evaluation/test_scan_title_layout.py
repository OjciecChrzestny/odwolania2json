"""Transfer titles read from spatially separated OCR cells."""
from dataclasses import replace
import unittest

from odwolania2json.bank_scan import ScanView, Word
from odwolania2json.extract import extract
from odwolania2json.model import Document, Extraction, load_classes
from odwolania2json.transfer_title import TITLE, apply_scan_title


def positions(*lines):
    rows = []
    for index, cells in enumerate(lines):
        row = []
        for left, text in cells:
            for token in text.split():
                width = 6 * len(token)
                row.append(Word(left, 18 * index, width, 12, token))
                left += width + 5
        rows.append(tuple(row))
    return tuple(rows)


def tsv(rows):
    return "\n".join(f"5\t1\t1\t1\t1\t1\t{w.x}\t{w.y}\t{w.width}\t{w.height}\t92\t{w.text}"
                     for row in rows for w in row)


class ScanTitleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = load_classes()
        cls.config = cls.classes["przelew"]
        cls.rules = cls.config["fields"][TITLE]

    def parse(self, raw, rows):
        doc = Document.from_pages(["POTWIERDZENIE PRZELEWU\nKwota: 3,24 PLN\n" + raw])
        return extract(replace(doc, ocr_layout_tsv=tsv(rows)), self.classes)

    def test_wrap_in_title_cell_with_receiver_on_the_same_rows(self):
        rows = positions(
            ((20, "Tytuł"), (240, "Zaliczka O-18,"), (610, "Odbiorca")),
            ((240, "etap II/07."), (610, "Pracownia Błękit")),
            ((20, "Dokument wygenerowany elektronicznie."),),
        )
        data, evidence = self.parse("Tytuł: Zaliczka O-18, etap II/07. Odbiorca Pracownia Błękit", rows)
        self.assertEqual(data["przelew_bankowy"]["tytul"], "Zaliczka O-18, etap II/07.")
        self.assertEqual(evidence["fields"][TITLE]["page"], 1)
        self.assertEqual(evidence["fields"][TITLE]["source"], "ocr")

    def test_empty_column_does_not_supply_receiver_or_footer(self):
        rows = positions(((20, "Tytuł:"), (610, "Odbiorca")),
                         ((610, "Pracownia Błękit"),),
                         ((20, "Dokument wygenerowany elektronicznie."),))
        data, _ = self.parse("Tytuł:\nOdbiorca: Pracownia Błękit", rows)
        self.assertIsNone(data["przelew_bankowy"]["tytul"])

    def test_two_views_must_agree_on_the_same_physical_page(self):
        rows = positions(((20, "Tytuł: Usługa OR/43"),), ((20, "etap II."),))
        doc = Document.from_pages(["Pierwsza strona", "Tytuł: Usługa QR/43\netap II."])
        result = Extraction(doc, self.config["schema"])
        result.put(("przelew_bankowy", "tytul"), "Usługa QR/43 etap II.", doc.starts[1][0],
                   "tytuł_z_etykiety", source="ocr")
        view = ScanView(2, "", (), positions=rows)
        apply_scan_title(result, self.rules, views=[replace(view, page=1), view])
        self.assertEqual(result.data["przelew_bankowy"]["tytul"], "Usługa QR/43 etap II.")
        apply_scan_title(result, self.rules, views=[view, view])
        self.assertEqual(result.data["przelew_bankowy"]["tytul"], "Usługa OR/43 etap II.")
        self.assertEqual(result.evidence[TITLE]["page"], 2)

    def test_skewed_rows_keep_the_label_and_title_in_source_order(self):
        rows = positions(
            ((20, "Potwierdzenie wykonania zlecenia płatniczego"),),
            ((20, "Tytułem"), (225, "Dostawa elementu kontrolnego według umowy nr 00072")),
            ((225, "w kwietniu, etap V."), (575, "Identyfikator wydruku")),
            ((20, "Kwota"), (225, "18,10 PLN")),
            ((20, "Dokument sporządzony elektronicznie bez podpisu"),),
        )
        skewed = tuple(tuple(replace(word, y=word.y + 35 - round(.032 * word.x)) for word in row)
                       for row in rows)
        data, _ = self.parse("Tytułem Dostawa elementu kontrolnego według umowy nr 00072", skewed)
        self.assertEqual(data["przelew_bankowy"]["tytul"],
                         "Dostawa elementu kontrolnego według umowy nr 00072 w kwietniu, etap V.")

    def test_a_bounded_dash_is_preserved_and_a_detached_mark_is_skipped(self):
        base = positions(((20, "Tytuł: Dostawa UK/2"),), ((20, "etap II"), (470, ".")))
        last = base[1][0]
        line = (last, Word(54, last.y + 7, 5, 2, "-"), Word(69, last.y, 30, 12, "mały"), base[1][-1])
        rows = (base[0], line)
        data, _ = self.parse("Tytuł: Dostawa UK/2", rows)
        self.assertEqual(data["przelew_bankowy"]["tytul"], "Dostawa UK/2 etap - mały")

    def test_case_is_taken_from_primary_when_visual_views_differ_only_in_case(self):
        doc = Document.from_pages(["Tylu!: Materiały SZ.09. Porcja 4"])
        result = Extraction(doc, self.config["schema"])
        readings = [ScanView(1, "", (), positions=positions(((20, text),))) for text in
                    ("Tytuł: materiały SZ.09, Porcja 4", "Tytuł: Materiały SZ.09, Porcja 4")]
        apply_scan_title(result, self.rules, views=readings)
        self.assertEqual(result.data["przelew_bankowy"]["tytul"], "Materiały SZ.09, Porcja 4")
        self.assertEqual(result.evidence[TITLE]["page"], 1)

    def test_keeps_primary_layout_when_classification_uses_a_different_reading(self):
        text = "Tytuł: Dopłata RV/921"
        rows = positions(((20, text),))
        # Alternate text can split a word. Its virtual offsets do not
        # describe the original reading's bounding boxes.
        alternate = Document.from_pages(["Tytuł: Dop łata RV/921"])
        original = replace(Document.from_pages([text]), ocr_layout_tsv=tsv(rows))
        result = Extraction(alternate, self.config["schema"])
        result.put(("przelew_bankowy", "tytul"), "Dop łata RV/921", 0, "tytuł_z_etykiety")
        view = ScanView(1, "", (), positions=rows)
        apply_scan_title(result, self.rules, views=[view], primary_document=original)
        self.assertEqual(result.data["przelew_bankowy"]["tytul"], "Dopłata RV/921")
        self.assertEqual(result.evidence[TITLE]["source"], "ocr")

    def test_native_title_is_preserved(self):
        doc = Document.from_pages(["Tytuł: Oryginał"])
        result = Extraction(doc, self.config["schema"])
        result.put(("przelew_bankowy", "tytul"), "Oryginał", 0, "tytuł_z_etykiety", source="text")
        view = ScanView(1, "", (), positions=positions(((20, "Tytuł: Inna wersja"),)))
        apply_scan_title(result, self.rules, views=[view, view])
        self.assertEqual(result.data["przelew_bankowy"]["tytul"], "Oryginał")
