import unittest
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

from odwolania2json.ocr import LocalOCR
from odwolania2json import power_name_ocr as verifier


KRS = "0001234567"
NIP = "1234563218"
IDENTITY = {"krs": KRS, "nip": NIP}
LEGAL = "„Północ + Rzeka” Atelier (PL) sp. z o.o."
OTHER = "Północ Atelier sp. z o.o."
GRANT = "niniejszym udziela pełnomocnictwa:\nadw. Ada Nurt"


def page(body):
    return "PEŁNOMOCNICTWO\n" + body + "\n" + GRANT


def company(name):
    return f"{name} z siedzibą w Modelowie, KRS: {KRS}, NIP: {NIP}"


def tsv(*words):
    return "\n".join(f"5\t1\t1\t1\t1\t{i}\t{5+25*i}\t30\t22\t18\t92\t{word}"
                     for i, word in enumerate(words, 1))


class DeclarationTest(unittest.TestCase):
    def test_own_legal_name_with_quotes_symbols_and_abbreviation(self):
        result = verifier._same_role_declaration(page("Mocodawca: " + company(LEGAL)), IDENTITY)
        self.assertEqual(result.name, LEGAL)
        self.assertIn("KRS: " + KRS, result.context)
        self.assertIn("NIP: " + NIP, result.context)

    def test_quoted_nomination_is_not_an_active_declaration(self):
        quoted = "Cytat:\n„" + page(company(OTHER)) + "”"
        self.assertIsNone(verifier._same_role_declaration(quoted, IDENTITY))
        model = "Wzór:\n" + page(company(OTHER))
        self.assertIsNone(verifier._same_role_declaration(model, IDENTITY))

    def test_two_entities_and_similar_lookalikes_with_different_identifiers(self):
        second = company(OTHER).replace(NIP, "9876543210").replace(KRS, "0001234568")
        for text in (page(company(LEGAL) + "\n" + second), page(second),
                     page(company(f"{LEGAL} i {OTHER}")),
                     page(f"Konsorcjum:\n1. {company(LEGAL)};\n2. {second}")):
            with self.subTest(text=text):
                self.assertIsNone(verifier._same_role_declaration(text, IDENTITY))

    def test_recipient_and_counsel_companies_are_not_principals(self):
        for role in ("Odbiorca", "Pełnomocnik"):
            self.assertIsNone(verifier._same_role_declaration(page(f"{role}: " + company(OTHER)), IDENTITY))
        document = page(company(LEGAL)) + "\nOdbiorca: " + OTHER + "\nPełnomocnik: " + OTHER
        self.assertEqual(verifier._same_role_declaration(document, IDENTITY).name, LEGAL)

    def test_crop_must_contain_unique_physical_words(self):
        words = ("Modelowa", "sp.", "z", "o.o.,")
        box = verifier._unique_name_box(tsv(*words), "Modelowa sp. z o.o.", 300, 100)
        self.assertIsNotNone(box)
        self.assertIsNone(verifier._unique_name_box(tsv(*words, *words), "Modelowa sp. z o.o.", 300, 100))


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.ocr = LocalOCR(Mock(), Mock(), Path("tessdata"))
        self.pdf = Path("neutralny.pdf")
        self.value = {
            "mocodawca": [{
                "data": {**IDENTITY, "typ":"osoba_prawna", "nazwa": OTHER, "imie_nazwisko":None},
                "podpisujacy":[{"imie_nazwisko":"Mira Kamień"}],
            }],
            "pelnomocnicy":[{"imie_nazwisko":"Ada Nurt", "pesel":12345678900}],
        }
        self.record = {
            "class":"pelnomocnictwo", "status":"ok",
            "fields": {f"mocodawca.0.data.{key}":{"page":2,"source":"ocr","rule":"dotychczasowy"}
                       for key in ("nazwa","krs","nip")},
        }

    def test_hook_modifies_only_one_field_and_its_evidence(self):
        before = deepcopy(self.value)
        original_evidence = deepcopy(self.record)
        evidence = {"page":2,"source":"ocr","rule":verifier.RULE,"snippet":LEGAL,"ocr_box":{"x":20}}
        with patch.object(verifier, "_read_name", return_value=(LEGAL,evidence)) as read:
            v,r = verifier.verify_power_name(self.pdf,self.ocr,self.value,self.record,[1,2])
        read.assert_called_once_with(self.pdf,self.ocr,2,IDENTITY,OTHER)
        self.assertEqual(self.value,before)
        self.assertEqual(self.record,original_evidence)
        self.assertEqual(type(v["pelnomocnicy"][0]["pesel"]),int)
        before["mocodawca"][0]["data"]["nazwa"] = LEGAL
        original_evidence["fields"]["mocodawca.0.data.nazwa"] = evidence
        self.assertEqual((v,r),(before,original_evidence))

    def test_hook_abstains_on_text_only_multiple_principals_and_identity_on_another_page(self):
        duo = deepcopy(self.value)
        duo["mocodawca"].append(deepcopy(duo["mocodawca"][0]))
        shifted = deepcopy(self.record)
        shifted["fields"]["mocodawca.0.data.nip"]["page"] = 3
        wrong_type = deepcopy(self.value)
        wrong_type["mocodawca"][0]["data"]["typ"] = "osoba_fizyczna"
        with patch.object(verifier, "_read_name") as read:
            for value,record,pages in ((duo,self.record,[2]), (self.value,shifted,[2,3]),
                                       (self.value,self.record,[]), (wrong_type,self.record,[2])):
                self.assertEqual(verifier.verify_power_name(self.pdf,self.ocr,value,record,pages),(value,record))
        read.assert_not_called()

    def test_native_reader_requires_same_literal_in_independent_crop(self):
        name = "Modelowa sp. z o.o."
        full, cropped = Mock(), Mock()
        full.GetUTF8Text.return_value = page(company(name))
        full.GetTSVText.return_value = tsv("Modelowa", "sp.", "z", "o.o.,")
        cropped.GetUTF8Text.return_value = name
        cropped.MeanTextConf.return_value = 92
        self.ocr.api_type.side_effect = [nullcontext(full), nullcontext(cropped)]
        source, bitmap, sheet = Mock(), Mock(), Mock()
        source.__getitem__ = Mock(return_value=sheet)
        sheet.get_size.return_value = (590,800)
        sheet.render.return_value = bitmap
        bitmap.width, bitmap.height, bitmap.n_channels, bitmap.stride, bitmap.buffer = 300,100,1,300,b"abc"
        self.ocr.document_type.return_value = source
        found = verifier._read_name(self.pdf,self.ocr,1,IDENTITY,OTHER)
        self.assertEqual(found[0], name)
        self.assertEqual(found[1]["ocr_box"]["dpi"],300)
        cropped.SetRectangle.assert_called_once()
        cropped.GetUTF8Text.return_value = OTHER
        self.ocr.api_type.side_effect = [nullcontext(full), nullcontext(cropped)]
        self.assertIsNone(verifier._read_name(self.pdf,self.ocr,1,IDENTITY,OTHER))
