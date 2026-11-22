"""Lokalny panel kontroli i demonstracyjnego przetwarzania PDF-ów."""
import argparse
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
from base64 import b64encode
from contextlib import closing
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from PIL import Image  # pypdfium2 udostępnia bitmapę jako obraz Pillow
from pypdfium2 import PdfDocument, PdfiumError

from odwolania2json.__main__ import json_bytes, output_lock, overlaps, state_directory
from odwolania2json.field_evidence import _transfer_rules
from odwolania2json.model import DEFAULT_CONFIG, load_classes
from odwolania2json.operations import normalize
from odwolania2json.review import (IDENTITY, REPORT_VERSION, config_digest, digest, inspect, journal_path,
                                   open_journal, read_report, report_path, save_decision)

STATIC = Path(__file__).with_name("static")
ASSETS = {"/": ("index.html", "text/html"), "/panel.css": ("panel.css", "text/css"),
          "/panel.js": ("panel.js", "text/javascript")}
MAX_REQUEST = 16_384
MAX_UPLOAD = 32 * 1024 * 1024
DEMO_MARKER = ".operator-panel-demo"
ROOT = Path(__file__).resolve().parents[1]
PDF_LOCK = Lock()


# Profil zamrożony w PROTOKOL.json. Rewizje obejmują kod ekstrakcji, pełną
# konfigurację, pracę bez weryfikatora zewnętrznego i domyślny limit stron OCR.
FIELD_CONFIG_SHA256 = "aaa89fd8fd3be3ddb2e8b033b9bf1a892645e8b0c377ac6872553de54f9f1246"
FIELD_TEXT_REVISION = "sha256:48a86b7e1d4420ea1f2314c8cd9026f844ca6710912a459be6adfafd34b06619"
FIELD_OCR_REVISION = "sha256:dd880da0445beacaa3fb541379f1a7974ec02c905236410ce1a22ba9106bba5a"
# Bramka prezentacji po E. Kwalifikacja do pomiaru jest od niej niezależna.
TEXT_EVIDENCE_MEASUREMENT = {'strong': False, 'correct': 0, 'total': 0, 'sample_pdfs': 72, 'marked_pdfs': 0}
FIELD_RULES = {
    "przelew_bankowy.kwota": ("kwota_operacji", "kwota_operacji", "Kwota"),
    "przelew_bankowy.data_operacji": ("data_transakcji", "data_operacji", "Data operacji"),
}
FIELD_CAPTURES = _transfer_rules()
CLASS_BLOCKERS = ("classification_conflict", "uncertain_negative", "unknown_profile",
                  "read_error", "review_policy_unavailable")


def _matches_field_value(path, value, snippet):
    rule, _, sample_label = FIELD_RULES[path]
    capture = FIELD_CAPTURES.get((path, rule))
    if not capture:
        return False
    pattern, operation = capture
    if operation == "money":
        if type(value) is not int and (type(value) is not float or not math.isfinite(value)):
            return False
    elif operation != "date" or not isinstance(value, str) or not value:
        return False
    match = pattern.fullmatch(f"{sample_label}: {snippet}")
    return bool(match and match[1] == snippet and normalize(snippet, operation) == value)


def eligible_fields(record, result):
    """Return source groups for the raw result, with a current view from review.inspect.

    Callers outside the panel must merge inspect's view into the diagnostic
    record and pass the decoded bytes returned by that same call.
    """
    if not isinstance(record, dict) or not isinstance(result, dict):
        return {}
    revision = record.get("extractor_revision")
    if (type(record.get("report_version")) is not int or record["report_version"] != REPORT_VERSION
            or record.get("class") != "przelew" or record.get("status") != "ok"
            or record.get("config_sha256") != FIELD_CONFIG_SHA256
            or revision not in (FIELD_TEXT_REVISION, FIELD_OCR_REVISION)):
        return {}

    review = record.get("review")
    state = record.get("review_status")
    if (not isinstance(review, dict) or review.get("profile") != "przelew"
            or review.get("status") not in ("review_required", "auto_accepted")
            or state not in (review["status"], "resolved")):
        return {}
    identity = {key: record.get(key) for key in IDENTITY}
    if (not isinstance(identity["input"], str) or not identity["input"]
            or any(not isinstance(identity[key], str) or not re.fullmatch(r"[0-9a-f]{64}", identity[key])
                   for key in ("pdf_sha256", "output_sha256"))
            or record.get("review_id") != digest(json.dumps(identity, sort_keys=True).encode("utf-8"))):
        return {}
    try:
        if digest(json_bytes(result)) != identity["output_sha256"]:
            return {}
    except (TypeError, ValueError, RecursionError):
        return {}

    corrected_field = None
    decision = record.get("decision")
    if state == "resolved":
        if (not isinstance(decision, dict) or decision.get("review_id") != record["review_id"]
                or any(decision.get(key) != value for key, value in identity.items())
                or decision.get("action") not in ("accepted", "corrected")):
            return {}
        if decision["action"] == "corrected":
            corrected_field = decision.get("field")
            if not isinstance(corrected_field, str) or not corrected_field:
                return {}
    elif decision is not None:
        return {}

    reasons = review.get("reasons")
    pages, signals, ocr_pages = (record.get(key) for key in ("pages", "signals", "ocr_pages"))
    fields, values = record.get("fields"), result.get("przelew_bankowy")
    if (not all(isinstance(items, list) and all(isinstance(item, dict) for item in items)
                for items in (reasons, pages, signals))
            or not isinstance(ocr_pages, list) or any(type(page) is not int or page < 1 for page in ocr_pages)
            or not isinstance(fields, dict) or not isinstance(values, dict)
            or any(reason.get("code") in CLASS_BLOCKERS for reason in reasons)):
        return {}

    eligible = {}
    for path, (rule, signal_rule, _) in FIELD_RULES.items():
        if path == corrected_field or any(reason.get("field") == path for reason in reasons):
            continue
        proof = fields.get(path)
        if (not isinstance(proof, dict) or proof.get("rule") != rule
                or proof.get("precision") != "snippet" or proof.get("kind", "support") != "support"):
            continue
        snippet, span, number, source = (proof.get(key) for key in ("snippet", "span", "page", "source"))
        if (not isinstance(snippet, str) or not snippet.strip() or "\f" in snippet
                or not isinstance(span, dict) or type(span.get("start")) is not int
                or type(span.get("end")) is not int or span["start"] < 0
                or span["end"] - span["start"] != len(snippet)
                or type(number) is not int or number < 1 or source not in ("text", "ocr")):
            continue
        on_page = [page for page in pages if type(page.get("page")) is int and page["page"] == number]
        if (len(on_page) != 1 or on_page[0].get("status") != "readable"
                or on_page[0].get("source") != source
                or (source == "ocr") != (number in ocr_pages)
                or (source == "ocr" and revision != FIELD_OCR_REVISION)):
            continue
        page_signals = {signal["rule"] for signal in signals if type(signal.get("page")) is int
                        and signal["page"] == number and isinstance(signal.get("rule"), str)}
        if {"nagłówek_przelewu", signal_rule} <= page_signals and _matches_field_value(
                path, values.get(path.rsplit(".", 1)[1]), snippet):
            eligible[path] = source
    return eligible


class PanelError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class Panel:
    def __init__(self, source, output, diagnostic, config):
        self.source = source.resolve()
        self.output = output.resolve()
        self.diagnostic = diagnostic.resolve()
        self.config = config.resolve()
        self.journal = journal_path(self.diagnostic)
        state = state_directory(self.output)
        roots = self.source, self.output, self.diagnostic, self.journal, state
        if any(overlaps(first, second) for index, first in enumerate(roots)
               for second in roots[index + 1:]):
            raise ValueError("Wejście, wyniki, diagnostyka, dziennik i ewidencja wymagają odrębnych ścieżek.")

    def records(self):
        if self.diagnostic.resolve() != self.diagnostic or not self.diagnostic.is_file():
            raise PanelError(HTTPStatus.SERVICE_UNAVAILABLE,
                             "Brak raportu diagnostyki. Przetwórz katalog wejściowy w CLI i odśwież panel.")
        return read_report(self.diagnostic)

    def record(self, name):
        try:
            return self.records()[name]
        except KeyError:
            raise PanelError(HTTPStatus.NOT_FOUND, "Dokumentu nie ma w raporcie.") from None

    def pdf_path(self, name):
        if "\\" in name:
            raise ValueError("Ścieżka PDF-u ma nieprawidłowy separator.")
        path = report_path(self.source, name, ".pdf")
        if path.resolve() != path:
            raise ValueError("Ścieżka PDF-u prowadzi przez dowiązanie.")
        return path

    def view(self, name, record, journal):
        try:
            self.pdf_path(name)
            result = report_path(self.output, record["output"], ".json")
            if result.resolve() != result:
                raise ValueError("Ścieżka wyniku prowadzi przez dowiązanie.")
            return inspect(record, journal, self.source, self.output)
        except ValueError as exc:
            return {"review_status": "unavailable", "review_id": None, "decision": None,
                    "path_error": str(exc)}, None

    def documents(self):
        with output_lock(self.output):
            records = self.records()
            with open_journal(self.journal) as journal:
                return [self.summary(name, record, journal) for name, record in records.items()]

    def summary(self, name, record, journal):
        view, _ = self.view(name, record, journal)
        return {"input": name, "class": record["class"], "status": view["review_status"],
                "reasons": record["review"]["reasons"]}

    def document(self, name):
        with output_lock(self.output):
            record = self.record(name)
            with open_journal(self.journal) as journal:
                view, contents = self.view(name, record, journal)
        classes = load_classes(self.config)
        configuration_matches = config_digest(classes) == record.get("config_sha256")
        schema = classes.get(record["class"], {}).get("schema") if configuration_matches else None
        raw = contents.decode("utf-8") if contents is not None else None
        result = json.loads(raw) if raw else None
        current = {**record, **view}
        return {**current, "result": result, "raw_json": raw, "schema": schema,
                "eligible_fields": eligible_fields(current, result) if configuration_matches else {},
                "text_evidence_measurement": TEXT_EVIDENCE_MEASUREMENT}

    def page(self, name, number, review_id):
        if number < 1:
            raise ValueError("Numer fizycznej strony zaczyna się od 1.")
        with output_lock(self.output):
            record = self.record(name)
            with open_journal(self.journal) as journal:
                view, _ = self.view(name, record, journal)
                if view["review_id"] != review_id or not review_id:
                    raise PanelError(HTTPStatus.CONFLICT, "Wersja podglądu się zmieniła. Odśwież dokument.")
            data = self.pdf_path(name).read_bytes()
            if digest(data) != record["pdf_sha256"]:
                raise PanelError(HTTPStatus.CONFLICT, "PDF zmienił się przed otwarciem podglądu.")
        return render_page(data, number)

    def decide(self, payload):
        name, review_id, action = (payload.get(key) for key in ("name", "review_id", "action"))
        if not isinstance(name, str) or not isinstance(review_id, str) or not re.fullmatch("[0-9a-f]{64}", review_id):
            raise ValueError("Wybierz dokument i odczytaj identyfikator aktualnego wyniku.")
        if action not in ("accept", "correct"):
            raise ValueError("Dostępne decyzje to akceptacja i korekta pola.")
        correction = {}
        if action == "correct":
            if not isinstance(payload.get("field"), str) or "value" not in payload:
                raise ValueError("Podaj pole i nową wartość.")
            correction = {"field": payload["field"], "value": payload["value"],
                          "classes": load_classes(self.config)}
        with output_lock(self.output):
            record = self.record(name)
            with open_journal(self.journal) as journal:
                view, _ = self.view(name, record, journal)
                if view["review_id"] != review_id:
                    raise PanelError(HTTPStatus.CONFLICT, "Wynik lub PDF się zmienił. Wczytaj najnowszy wynik.")
                return save_decision(journal, record, self.source, self.output, review_id,
                                     "accepted" if action == "accept" else "corrected", **correction)


class DemoWorkspace:
    """Jeden odrębny przebieg CLI na każdy nowy PDF."""

    def __init__(self, workspace, config, ocr_data):
        if workspace.is_symlink():
            raise ValueError("Katalog demonstracyjny nie może być dowiązaniem.")
        self.root = workspace.resolve()
        self.config = config.resolve()
        self.ocr_data = ocr_data.resolve() if ocr_data else None
        if self.ocr_data and not (self.ocr_data / "pol.traineddata").is_file():
            raise ValueError("Katalog --ocr-data musi zawierać pol.traineddata.")
        marker = self.root / DEMO_MARKER
        try:
            self.root.mkdir(mode=0o700)
        except FileExistsError:
            if marker.is_symlink() or not marker.is_file():
                raise ValueError("Podaj nowy katalog demonstracyjny lub katalog utworzony wcześniej przez panel.")
        else:
            marker.touch(mode=0o600, exist_ok=False)
        self.processing = Lock()

    def get_panel(self, run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise PanelError(HTTPStatus.NOT_FOUND, "Nie ma takiego przebiegu demonstracyjnego.")
        run = self.root / run_id
        source, output, reports = run / "input", run / "output", run / "diagnostics"
        diagnostic = reports / "run.json"
        if (not diagnostic.is_file() or any(path.resolve() != path
                                             for path in (run, source, output, reports, diagnostic))):
            raise PanelError(HTTPStatus.NOT_FOUND, "Nie ma gotowego przebiegu demonstracyjnego.")
        return Panel(source, output, diagnostic, self.config)

    def upload(self, data):
        if not self.processing.acquire(blocking=False):
            raise PanelError(HTTPStatus.CONFLICT, "Trwa przetwarzanie innego PDF-u. Spróbuj ponownie po jego zakończeniu.")
        try:
            return self.extract(data)
        finally:
            self.processing.release()

    def extract(self, data):
        run_id = uuid4().hex
        run = self.root / run_id
        run.mkdir(mode=0o700)
        source = run / "input"
        source.mkdir()
        (source / "dokument.pdf").write_bytes(data)
        command = [sys.executable, "-B", "-m", "odwolania2json", "--input", str(source),
                   "--output", str(run / "output"), "--diagnostics", str(run / "diagnostics" / "run.json"),
                   "--config", str(self.config)]
        if self.ocr_data:
            command.extend(("--ocr-data", str(self.ocr_data)))
        try:
            result = subprocess.run(command, cwd=ROOT, env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise PanelError(HTTPStatus.SERVICE_UNAVAILABLE, "Ekstrakcja przekroczyła limit 180 sekund.") from exc
        if result.returncode not in (0, 1):
            raise PanelError(HTTPStatus.SERVICE_UNAVAILABLE,
                             "Lokalny ekstraktor nie ukończył przebiegu. Sprawdź konfigurację i OCR.")
        return {"run": run_id, "read_error": result.returncode == 1}


def render_page(data, number):
    """Renderuje obraz strony, pomijając interaktywne elementy PDF."""
    try:
        with PDF_LOCK, PdfDocument(data) as pdf:
            if number > len(pdf):
                raise PanelError(HTTPStatus.NOT_FOUND, "Nie ma takiej fizycznej strony PDF-u.")
            with closing(pdf[number - 1]) as page:
                scale = min(2, 1600 / max(page.get_size()))
                with closing(page.render(scale=scale, draw_annots=False)) as bitmap:
                    image: Image.Image = bitmap.to_pil()
                    with BytesIO() as out:
                        image.save(out, format="PNG")
                        png = b64encode(out.getvalue()).decode("ascii")
                with closing(page.get_textpage()) as text_page:
                    text = text_page.get_text_range()
                return {"page": number, "page_count": len(pdf), "text": text,
                        "image": "data:image/png;base64," + png}
    except (PdfiumError, OSError, ZeroDivisionError) as exc:
        raise PanelError(HTTPStatus.UNPROCESSABLE_CONTENT, "Nie udało się wyrenderować strony PDF-u.") from exc


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        # Ścieżki żądań mogą zawierać nazwy dokumentów.
        pass

    def send(self, status, content, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; "
                         "img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
                         "form-action 'none'")
        self.end_headers()
        self.wfile.write(content)

    def reply(self, status, value):
        self.send(status, json.dumps(value, ensure_ascii=True, allow_nan=False).encode(), "application/json")

    def request_address(self, write=False):
        host = self.headers.get("Host", "")
        if not re.fullmatch(r"127\.0\.0\.1(?::[0-9]{1,5})?", host):
            raise PanelError(HTTPStatus.FORBIDDEN, "Otwórz panel przez adres 127.0.0.1.")
        if write and self.headers.get("Origin") != f"http://{host}":
            raise PanelError(HTTPStatus.FORBIDDEN, "Zapis jest dostępny w otwartym panelu.")
        address = urlsplit(self.path)
        if address.netloc or address.scheme:
            raise ValueError("Użyj ścieżki lokalnego panelu.")
        return address

    def do_GET(self):
        self.handle_api(self.get)

    def do_POST(self):
        self.handle_api(self.post)

    def handle_api(self, handler):
        try:
            handler()
        except PanelError as exc:
            self.reply(exc.status, {"error": str(exc)})
        except ValueError as exc:
            self.reply(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except (AttributeError, TypeError, KeyError):
            self.reply(HTTPStatus.BAD_REQUEST, {"error": "Żądanie lub raport zawiera nieprawidłowe dane."})
        except (OSError, sqlite3.Error):
            self.reply(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Pliki przebiegu lub dziennik są niedostępne."})

    def review_panel(self, query):
        if self.server.demo is None:
            return self.server.panel
        run_id, = query.get("run", [None])
        return self.server.demo.get_panel(run_id)

    def get(self):
        address = self.request_address()
        if address.path in ASSETS:
            filename, content_type = ASSETS[address.path]
            self.send(HTTPStatus.OK, (STATIC / filename).read_bytes(), content_type)
            return
        demo = self.server.demo
        if address.path == "/api/mode":
            self.reply(HTTPStatus.OK, {"upload_enabled": demo is not None, "max_upload_bytes": MAX_UPLOAD,
                                       "ocr_enabled": bool(demo and demo.ocr_data)})
            return
        query = parse_qs(address.query, strict_parsing=True, max_num_fields=4)
        if address.path == "/api/documents":
            result = [] if demo and "run" not in query else self.review_panel(query).documents()
        elif address.path in ("/api/document", "/api/page"):
            panel = self.review_panel(query)
            name, = query.get("name", [])
            if address.path == "/api/document":
                result = panel.document(name)
            else:
                number, = query.get("number", [])
                review_id, = query.get("review_id", [])
                result = panel.page(name, int(number), review_id)
        else:
            raise PanelError(HTTPStatus.NOT_FOUND, "Nie ma takiej strony panelu.")
        self.reply(HTTPStatus.OK, result)

    def body(self, maximum, *, oversized=HTTPStatus.BAD_REQUEST):
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0:
            raise ValueError("Żądanie nie zawiera danych.")
        if size > maximum:
            raise PanelError(oversized, "Przekroczono dopuszczalny rozmiar żądania.")
        data = self.rfile.read(size)
        if len(data) != size:
            raise ValueError("Żądanie zawiera niekompletne dane.")
        return data

    def post(self):
        address = self.request_address(write=True)
        content_type = self.headers.get_content_type()
        if address.path == "/api/upload" and self.server.demo:
            if content_type != "application/pdf":
                raise PanelError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Wybierz plik PDF.")
            data = self.body(MAX_UPLOAD, oversized=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            result = self.server.demo.upload(data)
            self.reply(HTTPStatus.CREATED, result)
            return
        if address.path != "/api/decision":
            raise PanelError(HTTPStatus.NOT_FOUND, "Nie ma takiej akcji panelu.")
        if content_type != "application/json":
            raise PanelError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Decyzja wymaga danych JSON.")
        payload = json.loads(self.body(MAX_REQUEST))
        if not isinstance(payload, dict):
            raise ValueError("Dane decyzji muszą być obiektem JSON.")
        json.dumps(payload, allow_nan=False)
        query = parse_qs(address.query, strict_parsing=True, max_num_fields=1) if self.server.demo else {}
        self.reply(HTTPStatus.OK, self.review_panel(query).decide(payload))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="katalog PDF-ów")
    parser.add_argument("--output", type=Path, help="katalog surowych wyników")
    parser.add_argument("--diagnostics", type=Path, help="plik raportu z istniejącej ekstrakcji")
    parser.add_argument("--demo-workspace", type=Path, help="oddzielny katalog dla nowych PDF-ów w panelu")
    parser.add_argument("--ocr-data", type=Path, help="katalog pol.traineddata dla nowych PDF-ów")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--bind", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1",
                        help="adres nasłuchu, 0.0.0.0 do kontenera z portem hosta na 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.demo_workspace and any((args.input, args.output, args.diagnostics)):
        parser.error("--demo-workspace jest osobnym trybem i nie przyjmuje --input, --output ani --diagnostics.")
    if args.ocr_data and not args.demo_workspace:
        parser.error("--ocr-data dotyczy nowych plików w trybie --demo-workspace.")
    try:
        demo = None
        panel = None
        if args.demo_workspace:
            demo = DemoWorkspace(args.demo_workspace, args.config, args.ocr_data)
        else:
            panel = Panel(args.input or Path("input"), args.output or Path("output"),
                          args.diagnostics or Path("diagnostics/last-run.json"), args.config)
        with ThreadingHTTPServer((args.bind, args.port), Handler) as server:
            server.panel = panel
            server.demo = demo
            print(f"Panel dostępny na http://127.0.0.1:{server.server_port}", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Błąd panelu: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
