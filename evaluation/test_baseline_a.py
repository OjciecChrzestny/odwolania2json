"""Regresje dla publicznego CLI, struktury i rozdzielenia ról."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from evaluation.check_outputs import check_outputs
from odwolania2json.extract import extract
from odwolania2json.model import Document, load_classes
from score import score

ROOT = Path(__file__).resolve().parents[1]


def write_pdf(path, text):
    pdf = PdfWriter()
    page = pdf.add_blank_page(width=600, height=800)
    if text:
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        content = DecodedStreamObject()
        lines = " Tj T* ".join(f"({line})" for line in text.splitlines())
        content.set_data(f"BT /F1 12 Tf 15 TL 40 750 Td {lines} Tj ET".encode("ascii"))
        page.replace_contents(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.write(path)


class CliTest(unittest.TestCase):
    def test_direction_rename_duplicates_negative_errors_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input" / "zagniezdzony"
            artifact = root / "output" / source.name
            first = "00123456789012345678901234"
            second = "00987654321098765432109876"
            receipt = "\n".join(["POTWIERDZENIE PRZELEWU", "Data operacji: 2026-01-02", "Kwota: 12,50 PLN",
                                 "Na rachunek: " + second, "Z rachunku: " + first,
                                 "Opis: Wpis za odwolanie", "Numer transakcji: 0000123"])
            write_pdf(source / "x.pdf", receipt)
            write_pdf(source / "y.PDF", receipt)
            write_pdf(source / "obcy.pdf", "Protokol omawia odwolanie oraz przelew i pelnomocnictwo.")
            write_pdf(source / "skan.pdf", "")
            (source / "uszkodzony.pdf").write_bytes(b"bad PDF")
            (source / "zz_dalej.pdf").write_bytes((source / "x.pdf").read_bytes())
            artifact.mkdir(parents=True)
            foreign = artifact / "obcy_uzytkownika.json"
            foreign.write_text('{"nie_usuwaj": true}', encoding="utf-8")
            env = {**os.environ, "PYTHONPATH": str(ROOT)}

            def cli(code):
                run = subprocess.run([sys.executable, "-m", "odwolania2json"], cwd=root, env=env,
                                     capture_output=True, text=True, encoding="utf-8", errors="replace")
                self.assertEqual(run.returncode, code, run.stderr)
                return json.loads((root / "diagnostics/last-run.json").read_bytes())["documents"]

            records = cli(1)
            self.assertEqual({Path(row["output"]).stem for row in records if row["status"] == "read_error"},
                             {"skan", "uszkodzony"})
            self.assertEqual((artifact / "obcy.json").read_bytes(), b"")
            self.assertFalse((artifact / "skan.json").exists())
            original = (artifact / "x.json").read_bytes()
            transfer = json.loads(original)["przelew_bankowy"]
            self.assertEqual((transfer["z_rachunku"], transfer["na_rachunek"]), (first, second))
            self.assertEqual(transfer["numer_transakcji"], "0000123")
            self.assertEqual(transfer["kwota"], 12.5)
            self.assertEqual((artifact / "y.json").read_bytes(), original)
            self.assertEqual((artifact / "zz_dalej.json").read_bytes(), original)

            (source / "x.pdf").rename(source / "inna.pdf")
            for filename in ("y.PDF", "skan.pdf", "uszkodzony.pdf"):
                (source / filename).unlink()
            self.assertEqual(cli(0), cli(0))
            self.assertEqual((artifact / "inna.json").read_bytes(), original)
            self.assertFalse((artifact / "x.json").exists())
            self.assertFalse((artifact / "y.json").exists())
            for path in source.iterdir():
                path.unlink()
            self.assertEqual(cli(0), [])
            self.assertEqual(list(artifact.glob("*.json")), [foreign])


class ExtensionTest(unittest.TestCase):
    def test_new_document_class_added_in_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            config = {"class": "zawiadomienie", "threshold": 1, "signals": [
                {"name": "nagłówek", "weight": 1, "pattern": "^ZAWIADOMIENIE$"},
            ], "schema": {"sygnatura": "text?", "termin": "date?"}, "fields": {
                "sygnatura": [{"name": "znak_sprawy", "pattern": "^Sygnatura: (.+)$"}],
                "termin": [{"name": "data_terminu", "pattern": "^Termin: (<DATE>)$", "operation": "date"}],
            }}
            (folder / "zawiadomienie.json").write_text(json.dumps(config), encoding="utf-8")
            document = Document.from_pages(["ZAWIADOMIENIE\nSygnatura: TEST/1\nTermin: 5 marca 2026"])
            data, evidence = extract(document, load_classes(folder))
            self.assertEqual(data, {"sygnatura": "TEST/1", "termin": "2026-03-05"})
            self.assertEqual(evidence["fields"]["termin"], {"page": 1, "rule": "data_terminu"})
            self.assertIsNone(extract(document, load_classes())[0])


class LegalRulesTest(unittest.TestCase):
    def test_two_reasons_and_no_unrelated_date(self):
        text = (
            "Warszawa, dnia 2 stycznia 2026 roku\nKrajowa Izba Odwoławcza\n"
            "Odwołujący: Przykładowa Firma\nZamawiający: Przykładowa Gmina\n"
            "ODWOŁANIE\nDziałając w imieniu spółki, wnoszę odwołanie wobec czynności "
            "Zamawiającego, polegających na:\n"
            "1) zaniechaniu odrzucenia oferty rywala;\n"
            "2) wyborze najkorzystniejszej oferty w dniu 1 stycznia 2026 r.\n"
        )
        data, diag = extract(Document.from_pages([text]), load_classes())
        self.assertEqual(data["OdwolanieKIO"]["czynnosc_powod_id"], 7)
        self.assertEqual(data["OdwolanieKIO"]["czynnosc_opis"], "Zaniechanie odrzucenia oferty")
        self.assertIsNone(data["OdwolanieKIO"]["czynnosc_dzien"])
        self.assertEqual(diag["first_allegation"]["page"], 1)
        self.assertFalse(diag["first_allegation"]["fallback"])

    def test_authorization_separates_people_and_missing_value(self):
        text = (
            "PEŁNOMOCNICTWO\nPrzykładowa Firma sp. z o.o., ul. Testowa 1, NIP 0001234567, "
            "udziela pełnomocnictwa: adw. Anna Nowak (nr wpisu: X1), "
            "r. pr. Jan Kowalski (nr wpisu: X2).\n"
            "Mocodawca:\n.............................\nJoanna Wiśniewska\nPrezes Zarządu\n"
            "Pełnomocnictwo przyjmuję:\n.............................\nadw. Anna Nowak\n"
        )
        data, _ = extract(Document.from_pages([text]), load_classes())
        self.assertEqual(data["mocodawca"][0]["data"]["nazwa"], "Przykładowa Firma sp. z o.o.")
        self.assertIsNone(data["mocodawca"][0]["data"]["krs"])
        self.assertEqual(data["mocodawca"][0]["podpisujacy"], [{"imie_nazwisko": "Joanna Wiśniewska"}])
        self.assertEqual(data["pelnomocnicy"], [{"imie_nazwisko": "Anna Nowak", "pesel": None},
                                               {"imie_nazwisko": "Jan Kowalski", "pesel": None}])


class ContractTest(unittest.TestCase):
    def test_micro_f1_does_not_cover_required_keys_or_negative_files(self):
        def put(path, value):
            path.write_text(json.dumps(value), encoding="utf-8")
            return hashlib.sha256(path.read_bytes()).hexdigest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            output.mkdir()
            one = put(root / "positive.pdf", "synthetic")
            two = put(root / "negative.pdf", "synthetic negative")
            expected = {"przelew_bankowy": {"data_operacji": None, "kwota": 1, "tytul": None,
                        "numer_transakcji": None, "z_rachunku": None, "na_rachunek": None}}
            reference = put(root / "reference.json", expected)
            manifest = {"documents": [
                {"input": "x.pdf", "pdf": "positive.pdf", "class": "przelew", "sha256": one,
                 "reference": "reference.json", "reference_sha256": reference},
                {"input": "y.pdf", "pdf": "negative.pdf", "class": "negative", "sha256": two,
                 "reference": None},
            ]}
            path = root / "manifest.json"
            put(path, manifest)
            diagnostics = {"documents": [
                {"output": "x.json", "class": "przelew", "status": "ok"},
                {"output": "y.json", "class": "negative", "status": "negative"},
            ]}
            classes = load_classes()
            del expected["przelew_bankowy"]["data_operacji"]
            put(output / "x.json", expected)
            (output / "y.json").write_bytes(b"")
            metric = score(root, output, path)
            self.assertEqual(metric["micro_f1"], 1)
            self.assertTrue(metric["valid_run"])
            contract = check_outputs(output, manifest, diagnostics, classes)
            self.assertFalse(contract["valid_contract"])
            self.assertIn("x.json: $.przelew_bankowy.data_operacji: brak wymaganego klucza", contract["errors"])

            expected["przelew_bankowy"]["data_operacji"] = None
            put(output / "x.json", expected)
            (output / "y.json").unlink()
            metric = score(root, output, path)
            self.assertEqual(metric["micro_f1"], 1)
            self.assertFalse(metric["valid_run"])
            contract = check_outputs(output, manifest, diagnostics, classes)
            self.assertFalse(contract["valid_contract"])
            self.assertEqual(contract["errors"], ["y.json: $: brak pliku wynikowego"])

            (output / "y.json").write_bytes(b"{}")
            self.assertFalse(check_outputs(output, manifest, diagnostics, classes)["valid_contract"])
            (output / "y.json").write_bytes(b"")
            self.assertTrue(check_outputs(output, manifest, diagnostics, classes)["valid_contract"])


if __name__ == "__main__":
    unittest.main()
