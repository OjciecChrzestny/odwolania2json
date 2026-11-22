"""Control the optional API decision without contacting a provider."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

from experiments.abc.adapters import HttpResponse
from experiments.transfer_api.negative_verifier import NegativeVerifier
from odwolania2json.__main__ import process
from odwolania2json.model import Document, load_classes


TEXT = "Zestawienie\nTyp transakcji: przelew\nStatus wykonano\nNumer transakcji: 0007"
RECORD = {"class": "negative", "status": "negative", "signals": [], "fields": {}, "ocr_pages": [1]}


def reply(kind="wykonany_przelew", anchor="Typ transakcji", evidence="Status wykonano"):
    message = json.dumps({"klasa": kind, "dowod_typu": anchor, "dowod_operacji": evidence})
    return {"model": "fixture", "choices": [{"finish_reason": "stop", "message": {"content": message}}],
            "usage": {"prompt_tokens": 70, "completion_tokens": 18}}


class NegativeVerifierTest(unittest.TestCase):
    def setUp(self):
        self.document = replace(Document.from_pages([TEXT]), scan_quality={"page_count": 1})
        self.classes = load_classes()

    def verifier(self, response, budget=1):
        self.transport = Mock(return_value=response)
        return NegativeVerifier("fixture", budget, transport=self.transport, render=lambda pdf: b"png")

    def check(self, verifier, record=RECORD):
        return verifier(Path("neutral.pdf"), self.document, self.classes, record)

    def test_confirmed_class_reuses_local_field_extractor(self):
        verifier = self.verifier(HttpResponse(200, json.dumps(reply()).encode()))
        value, report = self.check(verifier)
        self.assertEqual(report["class"], "przelew")
        self.assertEqual(value["przelew_bankowy"]["numer_transakcji"], "0007")
        self.assertEqual(report["fields"]["przelew_bankowy.numer_transakcji"]["page"], 1)
        self.assertEqual(report["scaleway_verifier"]["usage"]["prompt_tokens"], 70)
        self.assertEqual(report["signals"][0]["quotes"], ["Typ transakcji", "Status wykonano"])
        self.assertIsNone(self.check(verifier)[0])
        self.assertEqual(self.transport.call_count, 1)
        request = json.loads(self.transport.call_args.args[2])
        self.assertNotIn("neutral.pdf", json.dumps(request))

    def test_other_document_and_ungrounded_claim_keep_empty_result(self):
        for result, outcome in [(reply("inny_dokument", "", ""), "inny_dokument"),
                                 (reply(anchor="tekst z sufitu", evidence="inna fraza"), "bez_potwierdzenia_w_tekscie")]:
            verifier = self.verifier(HttpResponse(200, json.dumps(result).encode()))
            value, report = self.check(verifier)
            self.assertIsNone(value)
            self.assertEqual(report["scaleway_verifier"]["outcome"], outcome)

    def test_rate_limit_blocks_following_calls(self):
        verifier = self.verifier(HttpResponse(429, b""), 3)
        self.assertEqual(self.check(verifier)[1]["scaleway_verifier"]["outcome"], "http_429")
        self.assertEqual(self.check(verifier)[1]["scaleway_verifier"]["outcome"], "skipped_after_http_429")
        self.assertEqual(self.transport.call_count, 1)

    def test_unrelated_native_text_does_not_leave_machine(self):
        verifier = self.verifier(HttpResponse(200, b""))
        doc = replace(Document.from_pages(["Pismo procesowe"]), scan_quality={"page_count": 2})
        value, report = verifier(Path("potwierdzenie przelewu.pdf"), doc, self.classes, RECORD)
        self.assertIsNone(value)
        self.assertEqual(report["scaleway_verifier"]["outcome"], "not_eligible")
        self.transport.assert_not_called()

    def test_bad_provider_format_is_a_fallback(self):
        for raw in (b"[]", b"{", b'{"choices": [null]}'):
            verifier = self.verifier(HttpResponse(200, raw))
            value, report = self.check(verifier)
            self.assertIsNone(value)
            self.assertEqual(report["scaleway_verifier"]["outcome"], "invalid_response_or_transport")

    def test_normal_process_calls_verifier_before_writing_empty_file(self):
        def read_document(_pdf, _ocr, *, classes):
            return Document.from_pages([TEXT]), []
        def classify_as_negative(_doc, _classes):
            return None, {"status": "negative", "class": "negative", "signals": [], "fields": {}}
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "input").mkdir()
            (work / "input/pismo.pdf").write_bytes(b"fixture served by injected reader")
            for kind in ("inny_dokument", "wykonany_przelew"):
                verifier = self.verifier(HttpResponse(200, json.dumps(reply(kind)).encode()))
                output = work / kind
                self.assertEqual(process(work / "input", output, self.classes, work / (kind + ".json"),
                                         read_document=read_document, extract_document=classify_as_negative,
                                         negative_verifier=verifier), 0)
                data = (output / "pismo.json").read_bytes()
                if kind == "inny_dokument":
                    self.assertEqual(data, b"")
                else:
                    self.assertEqual(json.loads(data)["przelew_bankowy"]["numer_transakcji"], "0007")
