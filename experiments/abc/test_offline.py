"""Techniczny odbiór offline z PDF-ami generowanymi na potrzeby testu."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from odwolania2json.__main__ import json_bytes, process
from odwolania2json.extract import extract, read_pdf
from odwolania2json.legal import Fragment, first_allegation
from odwolania2json.model import load_classes

from .adapters import (Adapter, HttpResponse, IDS, PROVIDERS, TIMEOUT_SECONDS, encode,
                       https_post, sha256, shared_payload)
from .run import checked_descriptions, classify_document, run_variant


APPEAL_HEADER = (
    "Warszawa, dnia 4 stycznia 2026 roku\nKrajowa Izba Odwoławcza\n"
    "Odwołujący: Przykładowa Firma\nZamawiający: Przykładowa Gmina\nODWOŁANIE"
)
FIRST = "Zaniechanie odrzucenia oferty dnia 2 stycznia 2026"
SECOND = "Wybór najkorzystniejszej oferty dnia 1 stycznia 2026"
FORMAL = f"Zarzut 1: {FIRST}:\nUzasadnienie zarzutu.\nZarzut 2: {SECOND}"
UNMATCHED = "Zamawiający pozbawił wykonawcę prawa dalszego udziału w postępowaniu."
UNMATCHED_FORMAL = f"Zarzut 1: {UNMATCHED}\nZarzut 2: {SECOND}"
HINT = "Zamawiający w dniu 3 stycznia 2026 r. wykluczył wykonawcę"
TRANSFER = (
    "POTWIERDZENIE PRZELEWU\nData operacji: 2026-01-02\nKwota: 12,50 PLN\n"
    "Na rachunek: 00987654321098765432109876\nZ rachunku: 00123456789012345678901234\n"
    "Opis: Wpis za odwołanie\nNumer transakcji: 0000123"
)
POWER = (
    "PEŁNOMOCNICTWO\nPrzykładowa Firma sp. z o.o., ul. Testowa 1, NIP 0001234567, "
    "udziela pełnomocnictwa: adw. Anna Nowak (nr wpisu: X1)\n"
    "Mocodawca:\nPodpisano w imieniu spółki.\nPełnomocnictwo przyjmuję:\nadw. Anna Nowak"
)
NEGATIVE = "Protokół narady o fikcyjnych dokumentach."


def write_pdf(path, *pages):
    pdf = PdfWriter()
    unicode_chars = sorted({char for page in pages for char in page if ord(char) > 127})
    codes = {char: index for index, char in enumerate(unicode_chars, 128)}
    mapping = "\n".join(f"<{index:02x}> <{ord(char):04x}>" for char, index in codes.items())
    cmap = DecodedStreamObject()
    cmap.set_data((
        "begincmap\n1 begincodespacerange\n<00> <ff>\nendcodespacerange\n"
        f"{len(codes)} beginbfchar\n{mapping}\nendbfchar\nendcmap"
    ).encode("ascii"))
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
        NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        NameObject("/ToUnicode"): cmap,
    })
    for text in pages:
        page = pdf.add_blank_page(width=600, height=800)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        stream = DecodedStreamObject()
        lines = " T* ".join(f"<{bytes(codes.get(char, ord(char)) for char in line).hex()}> Tj"
                           for line in text.splitlines())
        stream.set_data(f"BT /F1 12 Tf 15 TL 40 750 Td {lines} ET".encode("ascii"))
        page.replace_contents(stream)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.write(path)


def completion(content, *, finish="stop"):
    return HttpResponse(200, encode({
        "choices": [{"finish_reason": finish, "message": {"content": content}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 8},
    }))


def ok(reason_id):
    return completion(json.dumps({"czynnosc_powod_id": reason_id}))


def records(root):
    return json.loads((root / "diagnostics/experiment.json").read_bytes())["documents"]


def output_tree(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*.json")}


def baseline(input_dir, root):
    classes = load_classes()
    code = process(input_dir, root / "output", classes, root / "diagnostics/extraction.json")
    if code:
        raise AssertionError(f"Kod A: {code}")
    shutil.copytree(input_dir, root / "input")


class OfflineTest(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.getaddrinfo"):
            blocker = patch(target, side_effect=AssertionError("Test przechwycił próbę użycia sieci"))
            blocker.start()
            self.addCleanup(blocker.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.classes = load_classes()
        self.descriptions = checked_descriptions(self.classes)

    def appeal(self, name, allegation=FORMAL):
        path = self.root / "input" / name
        write_pdf(path, APPEAL_HEADER, allegation)
        return path

    def test_actual_reader_and_selector_formal_list_and_preceding_action(self):
        samples = [
            (FORMAL, FIRST, 7, "2026-01-02", "pierwszy_numerowany_zarzut"),
            (f"Zarzut 1: {SECOND}", SECOND + "\n\f\n", 2,
             "2026-01-01", "pierwszy_numerowany_zarzut"),
            (f"{HINT}.\nZarzut 1: Uchybienie proceduralne:\nMowa o odrzuceniu oferty.",
             HINT, 3, "2026-01-03", "czynność_wprowadzająca_pierwszy_zarzut"),
            ("Zarzucam:\n1) zaniechanie odrzucenia oferty;\n2) wybór najkorzystniejszej oferty.",
             "zaniechanie odrzucenia oferty;\n", 7, None, "pierwsza_czynność_z_listy"),
        ]
        for index, (text, expected, reason, date, rule) in enumerate(samples):
            with self.subTest(rule=rule, reason=reason):
                doc, ocr_pages = read_pdf(self.appeal(f"{index}.pdf", text))
                original, details = extract(doc, self.classes)
                self.assertNotIn("decision_fragment", details)
                section = original["OdwolanieKIO"]
                self.assertEqual((section["czynnosc_powod_id"], section["czynnosc_dzien"]), (reason, date))
                requests = Mock(return_value=ok(12))
                predicted, diagnostics = classify_document(
                    doc, self.classes, self.descriptions, Adapter(PROVIDERS["B"], "placeholder", requests))
                request = json.loads(requests.call_args.args[2])
                fragment = request["messages"][1]["content"]
                self.assertEqual(fragment, expected)
                source = diagnostics["decision_source"]
                offset = source["start_offset"]
                self.assertEqual(doc.text[offset:offset + len(fragment)], fragment)
                self.assertEqual(source["fragment_sha256"], sha256(fragment.encode("utf-8")))
                self.assertEqual((source["rule"], source["page"], source["start_page"]), (rule, 2, 2))
                self.assertEqual(ocr_pages, [])
                section.update(czynnosc_powod_id=12, czynnosc_opis=self.descriptions["12"])
                self.assertEqual(json_bytes(original), json_bytes(predicted))

    def test_structured_allegation_without_a_rule(self):
        pdf = self.appeal("01-unmatched.pdf", UNMATCHED_FORMAL)
        document, _ = read_pdf(pdf)
        patterns = self.classes["odwolanie"]["patterns"]
        body = Fragment(document.text).after(patterns["header"]).slice(0, 8500)
        fragment, rule = first_allegation(body, patterns)
        expected_fragment = UNMATCHED + "\n"
        self.assertEqual((fragment.text, rule), (expected_fragment, "pierwszy_numerowany_zarzut"))
        a_root = self.root / "A"
        baseline(pdf.parent, a_root)
        a_output = (a_root / "output/01-unmatched.json").read_bytes()
        a_record, = json.loads((a_root / "diagnostics/extraction.json").read_bytes())["documents"]
        self.assertEqual(a_record["first_allegation"],
                         {"page": 2, "rule": "brak_jednoznacznej_reguły_czynności", "fallback": True})
        a_section = json.loads(a_output)["OdwolanieKIO"]
        self.assertEqual((a_section["czynnosc_powod_id"], a_section["czynnosc_dzien"]), (11, None))

        requests, request_hashes = [], []
        for label, model_id in (("B", 3), ("C", 8)):
            with self.subTest(variant=label):
                rpc = Mock(return_value=ok(model_id))
                root = self.root / label
                self.assertEqual(run_variant(pdf.parent, root, label, token="placeholder",
                                             transport=rpc, mode="test_technical"), 0)
                record, = records(root)
                result = (root / "output/01-unmatched.json").read_bytes()
                section = json.loads(result)["OdwolanieKIO"]
                outcome = record["experiment"]
                print(f"Regresja {label} | struktura {rule} | ID A 11 | "
                      f"ID wyjścia {section['czynnosc_powod_id']} | próby {rpc.call_count} | "
                      f"przyczyna {outcome['cause']} | bajty A {result == a_output}")
                self.assertEqual(rpc.call_count, 1, outcome)
                self.assertEqual((outcome["outcome"], outcome["cause"]), ("success", None))
                self.assertEqual(record["first_allegation"],
                                 {**a_record["first_allegation"], "reason_id": 11})
                self.assertEqual(record["allegation_structure"], {"rule": rule, "page": 2})
                source = record["decision_source"]
                self.assertEqual(source, {"rule": rule, "page": 2, "start_offset": fragment.offset,
                                          "start_page": 2, "end_page": 2,
                                          "fragment_sha256": sha256(expected_fragment.encode("utf-8"))})
                request = json.loads(rpc.call_args.args[2])
                self.assertEqual(request.pop("model"), PROVIDERS[label].model)
                self.assertEqual(request["messages"][1]["content"], expected_fragment)
                self.assertNotIn(SECOND, request["messages"][1]["content"])
                requests.append(request)
                request_hashes.append(outcome["request_sha256"])
                expected = json.loads(a_output)
                expected["OdwolanieKIO"].update(czynnosc_powod_id=model_id,
                                               czynnosc_opis=self.descriptions[str(model_id)])
                self.assertEqual(result, json_bytes(expected))

        if len(requests) == 2:
            self.assertEqual(requests[0], requests[1])
            self.assertEqual(request_hashes, [sha256(encode(requests[0]))] * 2)
            print(f"SHA-256 fragmentu {sha256(expected_fragment.encode('utf-8'))} | "
                  f"SHA-256 wspólnego żądania {request_hashes[0]}")

    def test_unmatched_allegation_provider_failure_continues_to_rule_matched_id_11(self):
        first = self.appeal("01-unmatched.pdf", UNMATCHED_FORMAL)
        self.appeal("02-rule-11.pdf", "Zarzut 1: Opis przedmiotu zamówienia z dnia 2 stycznia 2026.")
        a_root = self.root / "A"
        baseline(first.parent, a_root)
        a_tree = output_tree(a_root / "output")
        self.assertEqual(json.loads(a_tree["02-rule-11.json"])["OdwolanieKIO"]["czynnosc_dzien"],
                         "2026-01-02")
        failures = {"B": (HttpResponse(429, b""), "http_429"), "C": (TimeoutError(), "timeout")}
        for label, (failure, cause) in failures.items():
            with self.subTest(variant=label):
                rpc = Mock(side_effect=[failure, ok(11)])
                root = self.root / label
                self.assertEqual(run_variant(first.parent, root, label, token="placeholder",
                                             transport=rpc, mode="test_technical"), 0)
                self.assertEqual(rpc.call_count, 2)
                self.assertEqual(output_tree(root / "output"), a_tree)
                failed, later = records(root)
                self.assertEqual(failed["output"], "01-unmatched.json")
                self.assertEqual(failed["first_allegation"]["reason_id"], 11)
                self.assertTrue(failed["first_allegation"]["fallback"])
                self.assertEqual(failed["experiment"]["outcome"], "fallback")
                self.assertEqual(failed["experiment"]["cause"], cause)
                self.assertTrue(failed["experiment"]["attempted"])
                self.assertEqual(later["output"], "02-rule-11.json")
                self.assertEqual(later["first_allegation"], {"page": 2,
                                 "rule": "pierwszy_numerowany_zarzut", "reason_id": 11, "fallback": False})
                self.assertEqual(later["experiment"]["outcome"], "success")
                print(f"Awaria {label} | {cause} | 1 próba na pierwszy PDF | "
                      "bajty A True | kolejne rozpoznanie ID 11 przetworzone")

    def test_single_ocr_for_each_variant(self):
        pdf = self.root / "input" / "synthetic.pdf"
        write_pdf(pdf, "", FORMAL)
        for label in PROVIDERS:
            with self.subTest(label=label):
                ocr = Mock(return_value=[(0, APPEAL_HEADER)])
                rpc = Mock(return_value=ok(5))
                root = self.root / label
                self.assertEqual(run_variant(pdf.parent, root, label,
                                             token="placeholder", transport=rpc,
                                             mode="test_technical", ocr=ocr), 0)
                ocr.assert_called_once_with(pdf, 1)
                rpc.assert_called_once()
                self.assertEqual(records(root)[0]["ocr_pages"], [1])
                self.assertEqual(records(root)[0]["decision_source"]["page"], 2)

    def test_no_transport_for_other_classes_missing_key_or_no_fragment(self):
        folder = self.root / "input"
        for filename, text in (("transfer.pdf", TRANSFER), ("power.pdf", POWER),
                               ("negative.pdf", NEGATIVE)):
            write_pdf(folder / filename, text)
        self.appeal("empty.pdf", f"Zarzut 1:\nZarzut 2: {SECOND}")
        self.appeal("missing.pdf", "Pismo bez wyodrębnionych zarzutów.")
        a = self.root / "A"
        baseline(folder, a)
        expected = {
            "transfer.json": ("przelew", None), "power.json": ("pelnomocnictwo", None),
            "negative.json": ("negative", None),
            "empty.json": ("odwolanie", "no_reliable_fragment"),
            "missing.json": ("odwolanie", "no_reliable_fragment"),
        }
        for label in PROVIDERS:
            with self.subTest(label=label):
                rpc = Mock()
                root = self.root / label
                self.assertEqual(run_variant(folder, root, label, token="placeholder", transport=rpc,
                                             mode="test_technical"), 0)
                self.assertEqual(output_tree(root / "output"), output_tree(a / "output"))
                rows = {row["output"]: row for row in records(root)}
                self.assertEqual({name: (row["class"], row["experiment"].get("cause"))
                                  for name, row in rows.items()}, expected)
                self.assertEqual(rows["empty.json"]["allegation_structure"],
                                 {"page": 2, "rule": "pierwszy_numerowany_zarzut"})
                self.assertIsNone(rows["missing.json"]["allegation_structure"])
                for name in ("empty.json", "missing.json"):
                    self.assertNotIn("decision_source", rows[name])
                    self.assertTrue(rows[name]["first_allegation"]["fallback"])
                rpc.assert_not_called()

        eligible = self.appeal("eligible.pdf", UNMATCHED_FORMAL)
        for label in PROVIDERS:
            with self.subTest(label=label, cause="missing_key"):
                rpc = Mock()
                doc, _ = read_pdf(eligible)
                baseline_value, _ = extract(doc, self.classes)
                candidate, diagnostics = classify_document(
                    doc, self.classes, self.descriptions, Adapter(PROVIDERS[label], " ", rpc))
                self.assertEqual(json_bytes(candidate), json_bytes(baseline_value))
                self.assertEqual(diagnostics["experiment"]["cause"], "missing_key")
                self.assertTrue(diagnostics["first_allegation"]["fallback"])
                self.assertIn("fragment_sha256", diagnostics["decision_source"])
                rpc.assert_not_called()

    def test_https_framing_without_network(self):
        payload = shared_payload(FIRST, self.descriptions)
        for provider in PROVIDERS.values():
            host = provider.url.split("/")[2]
            api = Adapter(provider, "placeholder", https_post)
            with self.subTest(host=host), patch("experiments.abc.adapters.HTTPSConnection") as factory:
                connection = factory.return_value
                response = MagicMock()
                connection.getresponse.return_value.__enter__.return_value = response
                response.status = 200
                for reason_id in IDS:
                    response.read.return_value = ok(reason_id).body
                    returned, report = api.classify(payload)
                    self.assertEqual(returned, reason_id)
                    self.assertIsNone(report["cause"])
                factory.assert_called_with(host, timeout=TIMEOUT_SECONDS)
                method, route, body, headers = connection.request.call_args.args
                self.assertEqual((method, route), ("POST", "/v1/chat/completions"))
                self.assertEqual(json.loads(body), {**payload, "model": provider.model})
                self.assertEqual(headers["Content-Type"], "application/json")
                self.assertEqual(headers["Authorization"], "Bearer placeholder")
                self.assertEqual(connection.close.call_count, len(IDS))

                response.read.reset_mock()
                response.status = 307
                returned, report = api.classify(payload)
                self.assertIsNone(returned)
                self.assertEqual(report["cause"], "http_307")
                response.read.assert_not_called()
                self.assertEqual(connection.request.call_count, len(IDS) + 1)

    def test_faults_preserve_bytes_and_batch_continues_for_both_providers(self):
        failures = [
            (completion('{"czynnosc_powod_id":true}'), "invalid_answer_schema"),
            (completion('{"czynnosc_powod_id":"3"}'), "invalid_answer_schema"),
            (completion('{"czynnosc_powod_id":3.0}'), "invalid_answer_schema"),
            (ok(0), "invalid_answer_schema"), (ok(13), "invalid_answer_schema"),
            (completion('{"czynnosc_powod_id":3,"czynnosc_opis":"inny"}'), "invalid_answer_schema"),
            (completion('{"czynnosc_powod_id":3,"czynnosc_powod_id":4}'), "invalid_answer_json"),
            (completion('{"czynnosc_powod_id":'), "invalid_answer_json"),
            (HttpResponse(200, b"{"), "invalid_envelope_json"),
            (completion('{"czynnosc_powod_id":3}', finish="length"), "incomplete_or_filtered"),
            (HttpResponse(429, b"secret marker"), "http_429"),
            (TimeoutError("secret marker"), "timeout"),
            (ConnectionResetError("secret marker"), "transport_error"),
        ]
        for index in range(len(failures) + 1):
            folder = self.appeal(f"doc_{index:02}.pdf").parent
        a = self.root / "A"
        baseline(folder, a)
        a_tree = output_tree(a / "output")
        for label, provider in PROVIDERS.items():
            with self.subTest(label=label):
                rpc = Mock(side_effect=[response for response, _ in failures] + [ok(3)])
                root = self.root / label
                self.assertEqual(run_variant(folder, root, label, token="placeholder",
                                             transport=rpc, mode="test_technical"), 0)
                self.assertEqual(rpc.call_count, len(failures) + 1)
                for call in rpc.call_args_list:
                    url, headers, body, timeout = call.args
                    self.assertEqual(url, provider.url)
                    self.assertEqual(headers["Authorization"], "Bearer placeholder")
                    self.assertEqual(timeout, TIMEOUT_SECONDS)
                    self.assertEqual(json.loads(body)["model"], provider.model)
                tree = output_tree(root / "output")
                for index, (_, cause) in enumerate(failures):
                    name = f"doc_{index:02}.json"
                    experiment = records(root)[index]["experiment"]
                    self.assertEqual((experiment["outcome"], experiment["cause"]), ("fallback", cause))
                    self.assertIsInstance(experiment["transport_seconds"], float)
                    self.assertEqual(tree[name], a_tree[name])
                last = records(root)[-1]
                changed = json.loads(tree[last["output"]])
                preserved = json.loads(a_tree[last["output"]])
                preserved["OdwolanieKIO"].update(czynnosc_powod_id=3, czynnosc_opis=self.descriptions["3"])
                self.assertEqual(json_bytes(changed), json_bytes(preserved))
                self.assertEqual(changed["OdwolanieKIO"]["czynnosc_dzien"], "2026-01-02")
                self.assertEqual(last["experiment"]["outcome"], "success")
                report = (root / "diagnostics/experiment.json").read_text(encoding="utf-8")
                self.assertNotIn("placeholder", report)
                self.assertNotIn("secret marker", report)
                self.assertNotIn(FIRST, report)

    def test_compare_command_on_same_32_synthetic_pdfs(self):
        folder = self.root / "input"
        for index in range(10):
            case = f"case_{index:02}"
            self.appeal(f"{case}/appeal.pdf")
            write_pdf(folder / case / "power.pdf", POWER)
            write_pdf(folder / case / "transfer.pdf", TRANSFER if index else NEGATIVE)
        for index in range(2):
            write_pdf(folder / f"case_{index:02}/negative.pdf", NEGATIVE)
        a = self.root / "A"
        baseline(folder, a)
        (a / "time.txt").write_text("Elapsed (wall clock) time (h:mm:ss or m:ss): 0:01.42\n",
                                    encoding="utf-8")
        dataset = self.root / "dataset"
        shutil.copytree(folder, dataset)
        source_transfer = json.loads((a / "output/case_01/transfer.json").read_bytes())
        synthetic_manifest = []
        for pdf in sorted(folder.rglob("*.pdf")):
            relative = pdf.relative_to(folder)
            kind = {"appeal": "odwolanie", "power": "pelnomocnictwo",
                    "transfer": "przelew", "negative": "negative"}[relative.stem]
            entry = {"pdf": relative.as_posix(), "input": relative.as_posix(), "class": kind,
                     "sha256": sha256(pdf.read_bytes()), "reference": None}
            ref = relative.with_suffix(".json")
            if kind != "negative":
                data = (a / "output" / ref).read_bytes()
                gold = json.loads(data) if data else source_transfer
                if ref.as_posix() == "case_00/appeal.json":
                    gold["OdwolanieKIO"].update(czynnosc_powod_id=8, czynnosc_opis=self.descriptions["8"])
                reference = json_bytes(gold)
                (dataset / ref).write_bytes(reference)
                entry.update(reference=ref.as_posix(), reference_sha256=sha256(reference))
            synthetic_manifest.append(entry)
        manifest = self.root / "synthetic-32.json"
        manifest.write_bytes(json_bytes({"documents": synthetic_manifest}))

        b = Mock(side_effect=[ok(8), HttpResponse(429, b""), *[ok(7) for _ in range(8)]])
        c = Mock(side_effect=[ok(8), TimeoutError(), ok(1), *[ok(7) for _ in range(7)]])
        for label, rpc in (("B", b), ("C", c)):
            self.assertEqual(run_variant(folder, self.root / label, label, token="placeholder",
                                         transport=rpc, mode="test_technical"), 0)
            self.assertEqual(rpc.call_count, 10)
        for b_call, c_call in zip(b.call_args_list, c.call_args_list, strict=True):
            left, right = (json.loads(call.args[2]) for call in (b_call, c_call))
            self.assertNotEqual(left.pop("model"), right.pop("model"))
            self.assertEqual(left, right)
            schema = left["response_format"]["json_schema"]["schema"]
            self.assertEqual(schema["properties"]["czynnosc_powod_id"]["enum"], IDS)
            self.assertTrue(all(f"{key}. {self.descriptions[str(key)]}" in left["messages"][0]["content"]
                                for key in IDS))

        command = [
            sys.executable, "-m", "experiments.abc.compare", "--dataset", str(dataset),
            "--manifest", str(manifest), "--a", str(a), "--b", str(self.root / "B"),
            "--c", str(self.root / "C"),
        ]
        report = json.loads(subprocess.check_output(command))
        self.assertEqual((report["mode"], report["pdfs"], report["shared_request_hashes"]),
                         ("test_technical", 32, 10))
        stats = report["variants"]
        self.assertEqual(stats["A"]["batch_seconds"], 1.42)
        self.assertEqual([stats[label]["correct_reason_ids"] for label in "ABC"], [9, 10, 9])
        self.assertTrue(stats["B"]["delta_micro_f1_pp"] > 0)
        self.assertEqual(stats["C"]["delta_micro_f1_pp"], 0)
        self.assertEqual(stats["B"]["tp"], stats["A"]["tp"] + 2)
        self.assertEqual(stats["B"]["fp"], stats["A"]["fp"] - 2)
        self.assertEqual(stats["B"]["fn"], stats["A"]["fn"] - 2)
        self.assertEqual(stats["B"]["fallback_causes"], {"http_429": 1})
        self.assertEqual(stats["C"]["fallback_causes"], {"timeout": 1})
        for label in "ABC":
            variant = stats[label]
            self.assertEqual((variant["appeals"], variant["negatives"]), (10, 2))
            self.assertFalse(variant["valid_run"])
            self.assertEqual(variant["false_positive_documents"], 0)
            self.assertEqual(variant["confusion_matrix"]["przelew"]["negative"], 1)
        for label in "BC":
            variant = stats[label]
            self.assertEqual(variant["fallbacks_to_a"], 1)
            self.assertEqual((variant["prompt_tokens_reported"], variant["completion_tokens_reported"]),
                             (1080, 72))
            self.assertIsNone(variant["estimated_cost_eur_for_reported_tokens"])
            self.assertEqual(len(variant["documents"]), 32)
        tampered = self.root / "B/output/case_00/appeal.json"
        value = json.loads(tampered.read_bytes())
        value["OdwolanieKIO"]["czynnosc_dzien"] = None
        tampered.write_bytes(json_bytes(value))
        rejected = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("niedozwolona zmiana", rejected.stderr)
        print("Test techniczny 32 PDF, 10/10 wspólnych żądań. " +
              ", ".join(f"{key}={stats[key]['tp']}/{stats[key]['fp']}/{stats[key]['fn']} "
                        f"F1={stats[key]['micro_f1']:.6f}" for key in "ABC"))
