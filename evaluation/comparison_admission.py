"""Verify source custodian's seal before assigning cohorts to the measurement."""
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from .check_outputs import read_json

POSITIVE_CLASSES = {"odwolanie", "pelnomocnictwo", "przelew"}
BLIND = {"blind_full_cases", "blind_transfers", "page_review"}
PAGE_STATES = ("readable", "partial", "unreadable", "unassessed")


def nonempty(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def sha256(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def read_source_seal(binding, baseline, digest):
    path = Path(binding["path"]).resolve()
    if not sha256(binding["sha256"]) or digest(path) != binding["sha256"]:
        raise ValueError("Niezgodny SHA-256 pieczęci źródeł 01.")
    proof = read_json(path)
    issued = datetime.fromisoformat(proof["sealed_utc"])
    if (proof["version"] != 1 or proof["custodian"] != "01" or proof["base_sha"] != baseline
            or issued.utcoffset() != timedelta(0)):
        raise ValueError("Pieczęć źródeł 01 wymaga właściwej wersji, bazy, kustosza i czasu UTC.")
    return proof


def unavailable(config, name):
    reason = config.get("reason")
    if not nonempty(reason):
        raise ValueError(f"{name}: niedostępna kohorta wymaga przyczyny.")
    if any(key in config for key in ("manifest", "manifest_sha256", "dataset", "documents")):
        raise ValueError(f"{name}: wpis niedostępny powinien zawierać stan i przyczynę.")
    return {"status": "unavailable", "reason": reason}


def inventory_values(proof, key, valid):
    items = proof["control_inventory"][key]
    if not isinstance(items, list) or any(not valid(value) for value in items):
        raise ValueError(f"Nieprawidłowa ewidencja kontrolna 01: {key}.")
    return set(items)


def build_origins(proof, name, config, rows):
    certified = proof["cohorts"][name]
    if (certified.get("status") != "ready" or certified.get("manifest_sha256") != config["manifest_sha256"]
            or certified.get("labels") != config["labels"]):
        raise ValueError(f"{name}: manifest lub poświadczenie etykiet nie zgadza się z pieczęcią źródeł 01.")
    origins = {}
    for origin in certified["documents"]:
        entry = origin["input"]
        if entry in origins:
            raise ValueError(f"{name}: powtórzony dokument w ewidencji źródeł.")
        origins[entry] = origin
    if origins.keys() != {row["input"] for row in rows}:
        raise ValueError(f"{name}: ewidencja źródeł i manifest zawierają różne dokumenty.")
    for row in rows:
        origin = origins[row["input"]]
        if (not sha256(origin.get("pdf_sha256")) or origin["pdf_sha256"] != row["sha256"]
                or not sha256(origin.get("source_sha256"))
                or not all(nonempty(origin.get(key)) for key in ("source_document_id", "template_family"))):
            raise ValueError(f"{name}: niezgodny hash PDF-u lub brak pochodzenia i rodziny szablonu.")
    return origins, certified.get("cases", {})


def full_case_reason(name, rows, origins, cases):
    by_case = defaultdict(set)
    for row in rows:
        identity = origins[row["input"]].get("case_id")
        if not nonempty(identity) or identity not in cases:
            raise ValueError(f"{name}: dokument bez powiązania z poświadczoną sprawą.")
        by_case[identity].add(row["class"])
    if set(cases) != by_case.keys():
        raise ValueError(f"{name}: ewidencja spraw nie odpowiada dokumentom manifestu.")
    canonical = set()
    for entry in cases.values():
        source_case_id = entry.get("source_case_id")
        if not nonempty(source_case_id) or entry.get("authentic") is not True:
            return "Brak potwierdzenia autentyczności lub kanonicznego identyfikatora sprawy."
        if source_case_id in canonical:
            raise ValueError(f"{name}: zdublowane sprawy pod różnymi identyfikatorami.")
        canonical.add(source_case_id)
    complete = sum(POSITIVE_CLASSES <= classes for classes in by_case.values())
    if complete < 10 or complete != len(by_case):
        return f"Kompletne autentyczne sprawy z trzema typami: {complete}/{len(by_case)}. Wymagane co najmniej 10 i komplet każdej."
    if not any("negative" in types for types in by_case.values()):
        return "Brak rzeczywistego negatywu w kohorcie pełnych spraw."
    return None


def readiness_reason(mode, name, config, rows, origins, cases):
    if name == "blind_full_cases":
        return full_case_reason(name, rows, origins, cases)
    if name == "blind_transfers" and not {"przelew", "negative"} <= {row["class"] for row in rows}:
        return "Brak osobnej próby z przelewami i negatywami."
    if name == "page_review":
        if config["labels"] != ("human" if mode == "production" else "synthetic"):
            return "Brak niezależnych ocen człowieka dla pól i stron."
        for row in rows:
            pages = row.get("pages")
            count = origins.get(row["input"], {}).get("page_count")
            if (not isinstance(pages, list) or not pages
                    or origins and (type(count) is not int or count != len(pages))
                    or any(not isinstance(page, dict) or type(page.get("page")) is not int
                           or page["page"] != number or page.get("status") not in PAGE_STATES
                           for number, page in enumerate(pages, 1))):
                return "Brak kompletnej, niezależnej listy ocen stron."
    return None


def validate_disjoint(evidence, controls):
    hashes = {}
    source_ids = set()
    source_files = {}
    controlled_families = controls["template_families"] | {
        origin["template_family"] for origin in evidence.get("known_128", {}).values()
    }
    for name, origins in evidence.items():
        for origin in origins.values():
            family = origin["template_family"]
            if name in BLIND and family in controlled_families:
                raise ValueError(f"{name}: domieszanie rodziny szablonu z ewidencji kontrolnej.")

            source_id = origin["source_document_id"]
            if source_id in source_ids:
                raise ValueError(f"{name}: powtórzony dokument źródłowy lub jego fragment.")
            source_ids.add(source_id)
            source_hash = origin["source_sha256"]
            if source_hash in source_files and name != "blind_full_cases":
                raise ValueError(f"{name}: powtórzony pierwotny plik źródłowy.")
            source_files[source_hash] = name
            for value in {origin["pdf_sha256"], origin["source_sha256"]}:
                ownership = (name, origin.get("case_id"))
                if name in BLIND and value in controls["hashes"]:
                    raise ValueError(f"{name}: hash powtarza dokument z ewidencji kontrolnej.")
                if value in hashes and hashes[value] != ownership:
                    raise ValueError(f"{name}: hash powtórzony między kohortami lub sprawami.")
                hashes[value] = ownership
        pdf_hashes = [origin["pdf_sha256"] for origin in origins.values()]
        if len(pdf_hashes) != len(set(pdf_hashes)):
            raise ValueError(f"{name}: powtórzone bajty PDF-u w kohorcie.")


def admit(mode, requested, manifests, proof, cohort_names):
    if mode == "production" or proof is not None:
        if set(requested) != set(cohort_names) or proof is None:
            raise ValueError("Podaj pieczęć źródeł 01 i stan każdej z czterech kohort.")
        if set(proof["cohorts"]) != set(cohort_names):
            raise ValueError("Pieczęć 01 nie opisuje wszystkich czterech kohort.")
        controls = {
            "template_families": inventory_values(proof, "template_families", nonempty),
            "hashes": inventory_values(proof, "pdf_sha256", sha256) | inventory_values(proof, "source_sha256", sha256),
        }
        if mode == "production" and set(manifests) & BLIND and not (
            controls["template_families"] and controls["hashes"]
        ):
            raise ValueError("Dopuszczenie ślepej próby wymaga niepustej ewidencji kontrolnej hashy i rodzin.")
    else:
        if set(manifests) & {"blind_full_cases", "blind_transfers"}:
            raise ValueError("Kontrola ślepych kohort wymaga struktury pieczęci 01 również na syntetykach.")
        proof, controls = None, None

    result, evidence = {}, {}
    for name in cohort_names:
        config = requested.get(name, {"status": "unavailable", "reason": "Kohorta poza zakresem próby syntetycznej."})
        if config.get("status", "ready") == "unavailable":
            result[name] = unavailable(config, name)
            if proof:
                sealed = proof["cohorts"][name]
                if sealed["status"] != "unavailable" or unavailable(sealed, name) != result[name]:
                    raise ValueError(f"{name}: stan niedostępności nie zgadza się z pieczęcią 01.")
            continue
        rows = manifests[name]
        origins, cases = build_origins(proof, name, config, rows) if proof else ({}, {})
        if proof:
            evidence[name] = origins
        reason = readiness_reason(mode, name, config, rows, origins, cases)
        result[name] = {"status": "unavailable", "reason": reason} if reason else {
            "status": "ready", "documents": len(rows), "manifest_sha256": config["manifest_sha256"],
        }
        if not reason and name == "blind_full_cases":
            result[name]["authenticated_case_ids"] = len(cases)

    if proof:
        validate_disjoint(evidence, controls)
        by_cohort = {name: {origin["template_family"] for origin in origins.values()}
                     for name, origins in evidence.items() if result[name]["status"] == "ready"}
        for name, families in by_cohort.items():
            result[name]["template_families"] = len(families)
            shared = set().union(*(other for key, other in by_cohort.items() if key != name))
            result[name]["shared_template_families"] = sorted(families & shared)
    return result
