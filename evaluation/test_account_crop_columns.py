"""Keep a damaged account and its OCR retries within the labelled column."""
from unittest import TestCase
from unittest.mock import MagicMock, Mock

from odwolania2json.bank_accounts import PAYEE, PAYER, account_observations
from odwolania2json.bank_scan import Word, row_text
from odwolania2json.ocr import read_account_crops


def account(body):
    return f"{98 - int(body + '252100') % 97:02d}" + body


PAYER_NRB = account("112233445566778899001122")
PAYEE_NRB = account("998877665544332211009988")
DAMAGED = "I" + PAYER_NRB[1:]


class AccountCropColumnTest(TestCase):
    def retry(self, positions, readings):
        bitmap = Mock(buffer=b"0", width=450, height=120, n_channels=1, stride=450)
        api = Mock()
        api.GetUTF8Text.side_effect = readings
        reader = MagicMock()
        reader.return_value.__enter__.return_value = api
        return read_account_crops(positions, bitmap, reader, "."), api

    def test_repairs_only_the_damaged_sender_in_either_column_order(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                headings = ("Odbiorca", "Nadawca") if reverse else ("Nadawca", "Odbiorca")
                accounts = (PAYEE_NRB, DAMAGED) if reverse else (DAMAGED, PAYEE_NRB)
                positions = (
                    (Word(10, 0, 70, 14, headings[0]), Word(211, 0, 70, 14, headings[1])),
                    (Word(10, 35, 192, 14, accounts[0]), Word(209, 35, 191, 14, accounts[1])),
                )
                self.assertEqual(account_observations(row_text(positions), positions),
                                 {PAYEE: {PAYEE_NRB}})
                recovered, api = self.retry(positions, [PAYER_NRB, PAYER_NRB])
                self.assertEqual(account_observations(row_text(recovered), recovered),
                                 {PAYER: {PAYER_NRB}, PAYEE: {PAYEE_NRB}})
                self.assertEqual(api.SetRectangle.call_count, 2)
                for call in api.SetRectangle.call_args_list:
                    x, _, width, _ = call.args
                    if reverse:
                        self.assertGreaterEqual(x, 204)
                    else:
                        self.assertLessEqual(x + width, 204)

    def test_without_two_labelled_roles_close_numbers_do_not_support_a_crop(self):
        positions = (
            (Word(10, 0, 70, 14, "Szczegóły"),),
            (Word(10, 35, 192, 14, DAMAGED), Word(209, 35, 191, 14, PAYEE_NRB)),
        )
        recovered, api = self.retry(positions, [])
        self.assertEqual(recovered, positions)
        api.GetUTF8Text.assert_not_called()

    def test_rejects_inconsistent_readings_and_a_box_crossing_the_divider(self):
        headings = (Word(10, 0, 70, 14, "Nadawca"), Word(211, 0, 70, 14, "Odbiorca"))
        right = Word(209, 35, 191, 14, PAYEE_NRB)
        for width, readings, calls in ((192, [PAYER_NRB, PAYER_NRB[:-1]], 2),
                                       (197, [], 0)):
            with self.subTest(width=width):
                positions = (headings, (Word(10, 35, width, 14, DAMAGED), right))
                recovered, api = self.retry(positions, readings)
                self.assertEqual(recovered, positions)
                self.assertEqual(api.GetUTF8Text.call_count, calls)

    def test_wrapped_iban_requires_two_aligned_rows_in_its_labelled_cell(self):
        positions = (
            (Word(10, 0, 76, 14, "Rachunek nadawcy"), Word(211, 0, 110, 14, "Rachunek odbiorcy")),
            (Word(10, 35, 120, 14, "PL 02 1122 3344"), Word(209, 35, 191, 14, PAYEE_NRB)),
            (Word(10, 54, 175, 14, "5566 7788 9900 1122"),),
        )
        self.assertEqual(account_observations(row_text(positions), positions),
                         {PAYER: {PAYER_NRB}, PAYEE: {PAYEE_NRB}})
        counterexamples = (
            positions[:2] + ((Word(10, 54, 175, 14, "5566 7788 9900 1123"),),),
            positions[:2] + ((Word(26, 54, 175, 14, "5566 7788 9900 1122"),),),
            positions[:2] + ((Word(209, 54, 175, 14, "5566 7788 9900 1122"),),),
            (positions[0], (Word(10, 35, 120, 14, "02 1122 3344"), positions[1][1]), positions[2]),
        )
        for counterexample in counterexamples:
            self.assertEqual(account_observations(row_text(counterexample), counterexample),
                             {PAYEE: {PAYEE_NRB}})
