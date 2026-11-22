"""A missing counsel reading must preserve the appeal and the rest of the batch."""
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from odwolania2json.__main__ import process
from odwolania2json.model import load_classes
from test_baseline_a import write_pdf


class AppealCounselBatchTest(TestCase):
    def test_unreadable_counsel_does_not_abort_cli_batch(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source, output = directory / "input", directory / "output"
            diagnostics = directory / "report.json"
            ocr_text = {}
            for stem, representative in (
                ("01-nieczytelny", "???"),
                ("02-etykieta", "Kancelaria Testowa"),
                ("03-czytelny", "Iga Wrzos\ne-mail: w@example.invalid"),
            ):
                path = source / f"{stem}.pdf"
                write_pdf(path, "")
                ocr_text[path] = "\n".join((
                    "Krajowa Izba Odwoławcza", "Odwołujący: Proba Branzy sp. z o.o.",
                    f"reprezentowany przez: {representative}",
                    "Zamawiający: Gmina Fikcyjna", "ODWOŁANIE",
                    "Zarzut nr 1: zaniechanie odrzucenia oferty.",
                ))
            write_pdf(source / "04-przelew.pdf", "\n".join((
                "POTWIERDZENIE PRZELEWU", "Kwota: 20,65 PLN", "Data operacji: 2026-02-06",
            )))
            def ocr(path, stop, *, start=0):
                for page in range(start, stop):
                    yield page, ocr_text[path]

            with redirect_stdout(StringIO()):
                self.assertEqual(process(source, output, load_classes(), diagnostics, ocr), 0)
            rows = json.loads(diagnostics.read_bytes())["documents"]
            self.assertEqual([(row["output"], row["class"], row["status"]) for row in rows], [
                ("01-nieczytelny.json", "odwolanie", "ok"),
                ("02-etykieta.json", "odwolanie", "ok"),
                ("03-czytelny.json", "odwolanie", "ok"),
                ("04-przelew.json", "przelew", "ok"),
            ])
            for row in rows[:2]:
                appellant, = json.loads((output / row["output"]).read_bytes())["Odwolujacy"]
                self.assertEqual(appellant["nazwa"], "Proba Branzy sp. z o.o.")
                self.assertTrue(all(value is None for value in appellant["pelnomocnik"].values()))
            appellant, = json.loads((output / rows[2]["output"]).read_bytes())["Odwolujacy"]
            self.assertEqual(appellant["pelnomocnik"]["imie_nazwisko"], "Iga Wrzos")
            self.assertEqual(appellant["pelnomocnik"]["mail"], "w@example.invalid")
            transfer = json.loads((output / rows[3]["output"]).read_bytes())["przelew_bankowy"]
            self.assertEqual(transfer["kwota"], 20.65)
