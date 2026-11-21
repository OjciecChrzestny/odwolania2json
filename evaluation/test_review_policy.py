"""Syntetyczne obserwacje dla izolowanego odbioru polityki kontroli."""

import json
from unittest import TestCase

from odwolania2json.review_policy import decide_review

PAYER = "przelew_bankowy.z_rachunku"
PAYEE = "przelew_bankowy.na_rachunek"
REFERENCE = "przelew_bankowy.numer_transakcji"
AMOUNT = "przelew_bankowy.kwota"
READABLE = {"page": 1, "status": "readable", "reason": "native_text"}


def nrb(body):
    return f"{98 - int(body + '252100') % 97:02d}" + body


def evidence(snippet, *, page=1, **extra):
    return {"page": page, "rule": "synthetic_label", "source": "text",
            "precision": "snippet", "snippet": snippet, **extra}


class ReviewPolicyTest(TestCase):
    def setUp(self):
        self.bank = {
            "z_rachunku": nrb("112233445566112233445566"),
            "na_rachunek": nrb("998877665544998877665544"),
            "kwota": 42.5,
            "data_operacji": "2026-11-07",
            "tytul": "Płatność za usługę",
            "numer_transakcji": None,
        }
        self.fields = {
            PAYER: evidence("Rachunek obciążany " + self.bank["z_rachunku"], role="z_rachunku"),
            PAYEE: evidence("Rachunek uznawany " + self.bank["na_rachunek"], role="na_rachunek"),
            AMOUNT: evidence("Kwota 42,50"),
            "przelew_bankowy.data_operacji": evidence("Data wykonania 07.11.2026"),
            "przelew_bankowy.tytul": evidence("Tytuł: " + self.bank["tytul"]),
            REFERENCE: evidence("Identyfikator transakcji: —", kind="absent",
                                reason="Rubryka identyfikatora oznaczona kreską"),
        }

    def transfer(self, *, pages=(READABLE,), verified_profiles=("przelew",)):
        return decide_review("przelew", pages=pages, fields=self.fields,
                             value={"przelew_bankowy": self.bank},
                             verified_profiles=verified_profiles)

    def assert_reasons(self, decision, *reasons):
        self.assertEqual(decision["status"], "review_required")
        self.assertCountEqual(decision["reasons"], reasons)

    def test_readable_transfer_with_unconfirmed_account_role_requires_review(self):
        del self.fields[PAYER]["role"]
        self.assert_reasons(self.transfer(),
                            {"code": "account_role_unconfirmed", "field": PAYER, "page": 1})

    def test_corrupt_pdf_has_distinct_reason(self):
        self.assert_reasons(decide_review("read_error"), {"code": "read_error"})

    def test_classification_miss_is_an_uncertain_negative(self):
        self.assert_reasons(decide_review("negative", pages=[READABLE], verified_profiles=("negative",)),
                            {"code": "uncertain_negative"})

    def test_positive_negative_evidence_requires_a_verified_profile(self):
        proof = evidence("Potwierdzenie płatności kartą")
        default = decide_review("negative", pages=[READABLE], negative_evidence=[proof])
        self.assert_reasons(default, {"code": "profile_not_verified"})
        enabled = decide_review("negative", pages=[READABLE], negative_evidence=[proof],
                                verified_profiles=("negative",))
        self.assertEqual(enabled, {"status": "auto_accepted", "profile": "negative", "reasons": []})

    def test_conflicting_classifier_signals_block_a_supported_negative(self):
        decision = decide_review("negative", pages=[READABLE], negative_evidence=evidence("Płatność kartą"),
                                 classification_conflicts=[1], verified_profiles=("negative",))
        self.assert_reasons(decision, {"code": "classification_conflict", "page": 1})

    def test_negative_conflict_record_does_not_count_as_positive_support(self):
        conflict = evidence("Możliwe potwierdzenie przelewu", kind="conflict")
        self.assert_reasons(
            decide_review("negative", pages=[READABLE], negative_evidence=[conflict],
                          verified_profiles=("negative",)),
            {"code": "classification_conflict", "page": 1},
            {"code": "uncertain_negative", "page": 1},
        )

    def test_justified_optional_null_does_not_block(self):
        self.assertEqual(self.transfer(),
                         {"status": "auto_accepted", "profile": "przelew", "reasons": []})
        self.assert_reasons(self.transfer(verified_profiles=()), {"code": "profile_not_verified"})

    def test_absence_requires_a_precise_observation(self):
        self.fields[REFERENCE] = {"page": 1, "kind": "absent", "reason": "Brak odczytu"}
        self.assert_reasons(self.transfer(),
                            {"code": "optional_absence_unconfirmed", "field": REFERENCE, "page": 1})

    def test_blank_string_does_not_qualify_as_a_justified_null(self):
        self.bank["numer_transakcji"] = " "
        self.assert_reasons(self.transfer(),
                            {"code": "optional_absence_unconfirmed", "field": REFERENCE, "page": 1})

    def test_required_amount_cannot_be_null_even_with_absence_evidence(self):
        self.bank["kwota"] = None
        self.fields[AMOUNT] = evidence("Kwota: —", kind="absent", reason="Pusta rubryka")
        self.assert_reasons(self.transfer(),
                            {"code": "missing_required_value", "field": AMOUNT, "page": 1})

    def test_two_conflicting_role_candidates_keep_both_page_locations(self):
        self.bank["z_rachunku"] = None
        first = nrb("112233445566112233445566")
        second = nrb("001122334455001122334455")
        self.fields[PAYER] = [
            evidence("Rachunek płatnika " + first, role="z_rachunku", value=first),
            evidence("Nadawca " + second, page=2, role="z_rachunku", source="ocr", value=second),
        ]
        other = {**READABLE, "page": 2}
        baseline_order = self.transfer(pages=[READABLE, other])
        self.assert_reasons(
            baseline_order,
            {"code": "account_role_conflict", "field": PAYER, "page": 1},
            {"code": "account_role_conflict", "field": PAYER, "page": 2},
        )
        self.fields[PAYER].reverse()
        self.assertEqual(json.dumps(self.transfer(pages=[other, READABLE])), json.dumps(baseline_order))

    def test_one_nrb_in_both_roles_requires_review_even_with_a_valid_checksum(self):
        self.bank["na_rachunek"] = self.bank["z_rachunku"]
        self.fields[PAYEE]["snippet"] = "Rachunek uznawany " + self.bank["z_rachunku"]
        self.assert_reasons(self.transfer(),
                            {"code": "account_role_conflict", "field": PAYEE, "page": 1},
                            {"code": "account_role_conflict", "field": PAYER, "page": 1})

    def test_invalid_checksum_is_a_separate_reason(self):
        account = self.bank["z_rachunku"]
        self.bank["z_rachunku"] = account[:-1] + str((int(account[-1]) + 1) % 10)
        self.fields[PAYER]["snippet"] = "Rachunek obciążany " + self.bank["z_rachunku"]
        self.assert_reasons(self.transfer(),
                            {"code": "invalid_account_checksum", "field": PAYER, "page": 1})

    def test_bad_page_blocks_even_if_all_fields_have_readable_evidence(self):
        for state in ("partial", "unreadable", "unassessed"):
            with self.subTest(state=state):
                self.assert_reasons(self.transfer(pages=[READABLE, {"page": 2, "status": state}]),
                                    {"code": f"page_{state}", "page": 2})

    def test_page_gap_or_duplicate_blocks_the_document(self):
        self.assert_reasons(self.transfer(pages=[READABLE, {**READABLE, "page": 3}]),
                            {"code": "page_observations_incomplete"})
        self.assert_reasons(self.transfer(pages=[READABLE, READABLE]),
                            {"code": "page_observations_invalid", "page": 1})

    def test_page_hint_or_snippet_from_another_page_is_insufficient(self):
        for field in ({"page": 1, "precision": "page"}, evidence("Kwota 42,50", page=2),
                      evidence("  ")):
            with self.subTest(field=field):
                self.fields[AMOUNT] = field
                reason = {"code": "field_evidence_insufficient", "field": AMOUNT}
                if field["page"] == 1:
                    reason["page"] = 1
                self.assert_reasons(self.transfer(), reason)

    def test_mandate_and_appeal_have_distinct_required_roles(self):
        mandate = {"mocodawca": [{"data": {"typ": "osoba_fizyczna", "imie_nazwisko": None}}],
                   "pelnomocnicy": []}
        decision = decide_review("pelnomocnictwo", pages=[READABLE], value=mandate,
                                 fields={"mocodawca.0.data.typ": evidence("Jan Przykład")},
                                 verified_profiles=("pelnomocnictwo",))
        self.assert_reasons(decision,
                            {"code": "missing_required_value", "field": "mocodawca.0.data.imie_nazwisko"},
                            {"code": "missing_required_value", "field": "pelnomocnicy"})

        appeal = {"Odwolujacy": [{"nazwa": "Firma przykładowa"}],
                  "Zamawiajacy": [{"nazwa": "Gmina przykładowa"}],
                  "OdwolanieKIO": {"czynnosc_powod_id": 1, "czynnosc_opis": "Opis kanoniczny"}}
        wrong = {"Odwolujacy.0.nazwa": [
            evidence("Odwołujący Firma przykładowa", value="Firma przykładowa"),
            evidence("Odwołujący Inny podmiot", value="Inny podmiot"),
        ],
            "Zamawiajacy.0.nazwa": evidence("Zamawiający Gmina przykładowa"),
            "OdwolanieKIO.czynnosc_powod_id": evidence("Pierwszy zarzut"),
            "OdwolanieKIO.czynnosc_opis": evidence("Fragment odpowiadający opisowi"),
        }
        self.assert_reasons(
            decide_review("odwolanie", pages=[READABLE], fields=wrong, value=appeal,
                          verified_profiles=("odwolanie",)),
            {"code": "field_evidence_conflict", "field": "Odwolujacy.0.nazwa", "page": 1},
        )

    def test_conflict_survives_even_if_the_role_list_in_the_result_is_empty(self):
        mandate = {"mocodawca": [{"data": {"typ": "osoba_prawna", "nazwa": "Firma"},
                                  "podpisujacy": []}],
                   "pelnomocnicy": [{"imie_nazwisko": "Jan Przykład"}]}
        path = "mocodawca.0.podpisujacy.0.imie_nazwisko"
        fields = {
            "mocodawca.0.data.typ": evidence("Spółka"),
            "mocodawca.0.data.nazwa": evidence("Spółka Firma"),
            "pelnomocnicy.0.imie_nazwisko": evidence("Udziela Janowi Przykładowi"),
            path: evidence("Dwie sekcje z różnymi podpisami", kind="conflict"),
        }
        self.assert_reasons(
            decide_review("pelnomocnictwo", pages=[READABLE], fields=fields, value=mandate,
                          verified_profiles=("pelnomocnictwo",)),
            {"code": "field_evidence_conflict", "field": path, "page": 1},
        )

    def test_detected_signer_requires_a_name(self):
        mandate = {"mocodawca": [{"data": {"typ": "osoba_prawna", "nazwa": "Firma"},
                                  "podpisujacy": [{"imie_nazwisko": ""}]}],
                   "pelnomocnicy": [{"imie_nazwisko": "Jan Przykład"}]}
        path = "mocodawca.0.podpisujacy.0.imie_nazwisko"
        fields = {
            "mocodawca.0.data.typ": evidence("Spółka"),
            "mocodawca.0.data.nazwa": evidence("Spółka Firma"),
            "pelnomocnicy.0.imie_nazwisko": evidence("Udziela Janowi Przykładowi"),
            path: evidence("Podpis nieczytelny", kind="absent", reason="Brak nazwy przy podpisie"),
        }
        self.assert_reasons(
            decide_review("pelnomocnictwo", pages=[READABLE], fields=fields, value=mandate,
                          verified_profiles=("pelnomocnictwo",)),
            {"code": "missing_required_value", "field": path, "page": 1},
        )

    def test_unknown_class_stays_disabled(self):
        self.assert_reasons(decide_review("custom", pages=[READABLE], verified_profiles=("custom",)),
                            {"code": "unknown_profile"})
