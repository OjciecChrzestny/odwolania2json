"""Kolejka operatora i lokalny dziennik decyzji dla konkretnych wersji wyników."""
import hashlib
import json
import os
import sqlite3
import unicodedata
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .model import load_classes, schema_errors

try:
    from .field_evidence import with_field_sources
except ModuleNotFoundError as exc:
    if exc.name != f"{__package__}.field_evidence":
        raise
    with_field_sources = None

try:
    from .review_policy import decide_review
except ModuleNotFoundError as exc:
    if exc.name != f"{__package__}.review_policy":
        raise
    decide_review = None

from .extract import DEFAULT_OCR_PAGE_BUDGET


REPORT_VERSION = 1
IDENTITY = ("input", "pdf_sha256", "output_sha256", "extractor_revision")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pdf_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def config_digest(classes):
    return digest(json.dumps(classes, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def extractor_revision(config_sha256, ocr_enabled, *, ocr_page_budget=DEFAULT_OCR_PAGE_BUDGET, verifier_profile=None):
    # Ta sama kopia kodu i konfiguracji ma identyfikator również w obrazie bez .git.
    package = Path(__file__).parent
    parts = {path.name: digest(path.read_bytes()) for path in sorted(package.glob("*.py"))}
    parts.update(config=config_sha256, ocr=ocr_enabled)
    if ocr_enabled and ocr_page_budget is not None:
        parts["ocr_page_budget"] = ocr_page_budget
    if verifier_profile is not None:
        parts["negative_verifier"] = verifier_profile
    return "sha256:" + digest(json.dumps(parts, sort_keys=True).encode("utf-8"))


def review_details(document, record, value, ocr_enabled, *, read_error_quality=None):
    quality = getattr(document, "scan_quality", None) or read_error_quality
    if quality is not None:
        pages = quality["pages"]
    else:
        pages = [{"page": number, "status": "unassessed", "reason": "page_assessment_unavailable"}
                 for _, number in document.starts] if document is not None else []

    located_fields = {}
    for name, field in record["fields"].items():
        if isinstance(field, dict):
            evidence = {"precision": "page" if field.get("page") else "unavailable", **field}
            if not ocr_enabled and field.get("page") is not None and evidence.get("source") is None:
                evidence["source"] = "text"
            located_fields[name] = evidence
    if with_field_sources is not None:
        located_fields = with_field_sources(located_fields, ocr_pages=record.get("ocr_pages", ()))
    fields = {**record["fields"], **located_fields}

    if decide_review is None:
        reason = "read_error" if record["status"] == "read_error" else "review_policy_unavailable"
        review = {"status": "review_required", "profile": record["class"], "reasons": [{"code": reason}]}
    else:
        review = decide_review(record["class"], pages=pages, fields=fields, value=value)
    details = {"pages": pages, "fields": fields, "review": review}
    if quality is not None:
        details["scan_quality"] = {key: item for key, item in quality.items() if key != "pages"}
    return details


def journal_path(diagnostics):
    return diagnostics.with_suffix(".decisions.sqlite3")


@contextmanager
def open_journal(path):
    if path.is_symlink():
        raise ValueError(f"Dziennik decyzji jest dowiązaniem symbolicznym: {path}")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
    with closing(sqlite3.connect(path, timeout=30)) as journal, journal:
        journal.execute("CREATE TABLE IF NOT EXISTS decisions "
                        "(review_id TEXT PRIMARY KEY NOT NULL, payload TEXT NOT NULL)")
        yield journal


def read_report(path):
    documents = json.loads(path.read_bytes())["documents"]
    records = {}
    for record in documents:
        if record.get("report_version") != REPORT_VERSION:
            raise ValueError("Nieobsługiwana diagnostyka kontroli. Uruchom ponownie ekstrakcję.")
        name = record["input"]
        if name in records:
            raise ValueError(f"Powtórzona ścieżka PDF w diagnostyce: {name!r}")
        records[name] = record
    return records


def report_path(root, name, suffix):
    relative = PurePosixPath(name)
    path = root / relative
    if (relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name
            or path.suffix.lower() != suffix or not path.resolve().is_relative_to(root)):
        raise ValueError(f"Niebezpieczna ścieżka w diagnostyce: {name!r}")
    return path


def current_result(record, input_dir, output_dir):
    """Sprawdza aktualność bajtów. Brak wyniku i pusty wynik mają różne znaczenie."""
    source = report_path(input_dir, record["input"], ".pdf")
    result = report_path(output_dir, record["output"], ".json")
    if source.relative_to(input_dir).with_suffix(".json") != result.relative_to(output_dir):
        raise ValueError("Ścieżki PDF-u i wyniku JSON w diagnostyce nie pasują do siebie.")
    try:
        if not source.is_file() or result.is_symlink():
            return "stale", None
        if record["pdf_sha256"] is None:
            return "unavailable", None
        if pdf_digest(source) != record["pdf_sha256"]:
            return "stale", None
        if record["output_sha256"] is None:
            return ("stale" if result.exists() else "unavailable"), None
        contents = result.read_bytes()
    except (FileNotFoundError, IsADirectoryError):
        return "stale", None
    except PermissionError:
        return "unavailable", None
    if digest(contents) != record["output_sha256"]:
        return "stale", None
    return "current", contents


def inspect(record, journal, input_dir, output_dir):
    state, contents = current_result(record, input_dir, output_dir)
    if state != "current":
        return {"review_status": state, "review_id": None, "decision": None}, contents

    identity = {key: record[key] for key in IDENTITY}
    review_id = digest(json.dumps(identity, sort_keys=True).encode("utf-8"))
    row = journal.execute("SELECT payload FROM decisions WHERE review_id = ?", (review_id,)).fetchone()
    decision = json.loads(row[0]) if row else None
    status = "resolved" if decision else record["review"]["status"]
    return {"review_status": status, "review_id": review_id, "decision": decision}, contents


def correction(record, contents, field, value, classes):
    if not contents:
        raise ValueError("Pusty wynik nie zawiera pól do korekty.")
    if record["config_sha256"] != config_digest(classes):
        raise ValueError("Do korekty użyj konfiguracji klas z przebiegu ekstrakcji (--config).")

    result = json.loads(contents)
    keys = field.split(".")
    target = result
    for part in keys[:-1]:
        if isinstance(target, dict) and part in target:
            target = target[part]
        elif isinstance(target, list) and part.isascii() and part.isdecimal() and int(part) < len(target):
            target = target[int(part)]
        else:
            raise ValueError(f"Nie ma pola {field!r} w wyniku.")
    key = keys[-1]
    if not isinstance(target, dict) or key not in target:
        raise ValueError(f"Nie ma pola {field!r} w wyniku.")
    original = target[key]
    if isinstance(original, (dict, list)) or isinstance(value, (dict, list)):
        raise ValueError("Korekta przyjmuje pojedynczą wartość JSON.")
    if type(value) is type(original) and value == original:
        raise ValueError("Korekta musi zmieniać wartość pola.")
    target[key] = value
    errors = list(schema_errors(result, classes[record["class"]]["schema"]))
    if errors:
        raise ValueError("Nieprawidłowa korekta: " + ", ".join(errors))
    return {"field": field, "original_value": original, "corrected_value": value}


def save_decision(journal, record, input_dir, output_dir, expected, action, field=None, value=None,
                  classes=None):
    journal.execute("BEGIN IMMEDIATE")
    view, contents = inspect(record, journal, input_dir, output_dir)
    if view["review_id"] != expected or expected is None:
        raise ValueError("Wynik się zmienił lub jest niedostępny. Sprawdź ponownie poleceniem review show.")
    if record["review"]["status"] != "review_required":
        raise ValueError("Dokument nie jest skierowany do kontroli.")

    payload = {"action": action, "review_id": expected, **{key: record[key] for key in IDENTITY}}
    if action == "corrected":
        payload.update(correction(record, contents, field, value, classes))
    previous = view["decision"]
    if previous:
        same_payload = previous == {**payload, "decided_at": previous["decided_at"]}
        same_value_type = type(previous.get("corrected_value")) is type(payload.get("corrected_value"))
        if same_payload and same_value_type:
            return previous
        raise ValueError("Dla tej wersji wyniku istnieje już inna decyzja.")

    # Ponowna kontrola przed zapisem ogranicza okno wyścigu z zewnętrznym edytorem.
    if current_result(record, input_dir, output_dir)[0] != "current":
        raise ValueError("Pliki zmieniły się w trakcie kontroli.")
    payload["decided_at"] = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    journal.execute("INSERT INTO decisions (review_id, payload) VALUES (?, ?)",
                    (expected, json.dumps(payload, ensure_ascii=False, allow_nan=False)))
    return payload


def print_review(value):
    # Fragmenty PDF i ścieżki pozostają tekstem także w terminalu.
    rendered = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    print("".join(json.dumps(char)[1:-1] if unicodedata.category(char) in {"Cc", "Cf", "Cs"}
                  and char != "\n" else char for char in rendered))


def run_review(args, input_dir, output_dir, diagnostic):
    records = read_report(diagnostic)
    with open_journal(journal_path(diagnostic)) as journal:
        if args.action == "list":
            queue = []
            for name, record in records.items():
                view, _ = inspect(record, journal, input_dir, output_dir)
                if view["review_status"] not in {"resolved", "auto_accepted"}:
                    queue.append({"input": name, "class": record["class"],
                                  "review_status": view["review_status"],
                                  "reasons": record["review"]["reasons"]})
            print_review(queue)
            return 0

        if args.pdf not in records:
            raise ValueError(f"PDF nie występuje w diagnostyce: {args.pdf!r}")
        record = records[args.pdf]
        if args.action == "show":
            view, contents = inspect(record, journal, input_dir, output_dir)
            print_review({**record, **view, "result": json.loads(contents) if contents else None})
        else:
            if args.action == "correct":
                try:
                    value = json.loads(args.value)
                    json.dumps(value, allow_nan=False)
                except ValueError as exc:
                    raise ValueError("--value wymaga poprawnej wartości JSON.") from exc
                result = save_decision(journal, record, input_dir, output_dir, args.expect,
                                       "corrected", args.field, value, load_classes(args.config))
            else:
                result = save_decision(journal, record, input_dir, output_dir, args.expect, "accepted")
            journal.commit()
            print_review(result)
    return 0
