"""Odbiór rozpoznawania przelewów na niezależnych syntetycznych PDF-ach."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_baseline_a import ROOT, write_pdf


class TransferHeaderTest(unittest.TestCase):
    def test_bank_headers_and_lookalikes(self):
        sender = "00376100310001020304051801"
        recipient = "00592700110006070809102902"
        body = "\n".join([
            f"Na rachunek: {recipient}",
            f"Rachunek nadawcy: {sender}",
            "Data operacji: 2026-02-18",
            "Kwota: 42,75 PLN",
            "Opis: Oplata za materialy testowe",
            "Identyfikator operacji: 000745",
        ])
        headings = {
            "polecenie": "Bank Polny\nPOLECENIE PRZELEWU",
            "transakcja": "Bank Sokoli   Potwierdzenie transakcji",
            "operacja_bankowa": "POTWIERDZENIE WYKONANIA OPERACJI BANKOWEJ",
            "krajowy": "Potwierdzenie realizacji przelewu krajowego",
            "zlamany_po_potwierdzeniu": "Bank Potok\nPOTWIERDZENIE\nWYKONANIA PRZELEWU",
            "zlamany_przed_przelewem": "Bank Las\nPotwierdzenie realizacji\n  przelewu krajowego",
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expectations = {}
            for number, (case, heading) in enumerate(headings.items()):
                name = f"doc_{number:02}"
                write_pdf(root / "input" / f"{name}.pdf", f"{heading}\n{body}")
                expectations[case] = name

            write_pdf(root / "input/doc_20.pdf",
                      f"WEZWANIE DO ZAPLATY\nRachunek odbiorcy: {recipient}\nKwota: 42,75 PLN")
            write_pdf(root / "input/doc_21.pdf",
                      f"INSTRUKCJA DLA OFERENTOW\nPotwierdzenie wykonania\n"
                      f"przelewu trzeba dolaczyc do oferty.\nPrzyklad wypelnienia:\n{body}")
            run = subprocess.run([sys.executable, "-m", "odwolania2json"], cwd=root,
                                 env={**os.environ, "PYTHONPATH": str(ROOT)},
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)

            expected = {"przelew_bankowy": {
                "data_operacji": "2026-02-18", "kwota": 42.75, "tytul": "Oplata za materialy testowe",
                "numer_transakcji": "000745", "z_rachunku": sender, "na_rachunek": recipient,
            }}
            for case, name in expectations.items():
                with self.subTest(case=case):
                    data = (root / "output" / f"{name}.json").read_bytes()
                    self.assertNotEqual(data, b"", "Poprawny przelew otrzymał pusty wynik")
                    self.assertEqual(json.loads(data), expected)

            for name in ("doc_20", "doc_21"):
                with self.subTest(negative=name):
                    self.assertEqual((root / "output" / f"{name}.json").read_bytes(), b"")
