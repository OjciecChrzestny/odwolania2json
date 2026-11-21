"""Date anchors regressions on synthetic OCR tokens without a model or PDFs."""
import unittest

from .dates import date_cells


def word(x, y, text, width=None):
    return x, y, width or len(text) * 7, 14, text


class DateAnchorTest(unittest.TestCase):
    def test_explicit_anchor_suppresses_generation_and_title_dates(self):
        rows = [[word(10, 10, "Wygenerowano:"), word(160, 10, "06.01.2026")],
                [word(10, 80, "Data"), word(46, 80, "operacji")],
                [word(220, 80, "4"), word(234, 80, "stycznia"), word(295, 80, "2026")],
                [word(10, 124, "Tytuł"), word(160, 124, "05.01.2026")]]
        dates = date_cells(rows)
        self.assertEqual(len(dates), 1)
        box, role, anchor, tokens = dates[0]
        self.assertEqual((box[:2], role, anchor[:2], len(tokens)), ((220, 80), "operacji", (10, 80), 3))

    def test_print_only_or_unlabelled_date_yields_no_panel_candidates(self):
        for text in ("Wydrukowano", "Dokument", "Wygenerowano:"):
            self.assertFalse(date_cells([[word(5, 5, text), word(150, 5, "17.10.2025")]]))
        self.assertFalse(date_cells([[word(5, 5, "Data"), word(38, 5, "spotkania"), word(150, 5, "17.10.2025")]]))

    def test_two_columns_keep_only_the_execution_date(self):
        rows = [[word(10, 40, "Data"), word(46, 40, "wykonania"),
                 word(208, 40, "Data"), word(244, 40, "wydruku")],
                [word(10, 61, "15.02.2025"), word(208, 61, "23.02.2025")]]
        self.assertEqual([(r[0][:2], r[1]) for r in date_cells(rows)], [((10, 61), "wykonania")])

    def test_date_in_title_cannot_fill_empty_date_cell(self):
        rows = [[word(10, 40, "Data"), word(47, 40, "operacji"), word(180, 40, "Tytuł"),
                 word(303, 40, "08.04.2025")]]
        self.assertEqual(date_cells(rows), [])

    def test_month_word_must_be_contiguous_and_approved(self):
        for word2, xpos in (("umowa", 20), ("maja", 190)):
            rows = [[word(8, 40, "Data"), word(45, 40, "realizacji")],
                    [word(8, 63, "4"), word(xpos, 63, word2), word(xpos + 34, 63, "2025")]]
            self.assertEqual(date_cells(rows), [])
