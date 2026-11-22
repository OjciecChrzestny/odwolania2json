"""Lokalny panel kontroli istniejących wyników Odwołania2JSON."""
import argparse
import json
import re
import sqlite3
from base64 import b64encode
from contextlib import closing
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlsplit

from PIL import Image  # pypdfium2 udostępnia bitmapę jako obraz Pillow
from pypdfium2 import PdfDocument, PdfiumError

from odwolania2json.__main__ import output_lock, overlaps, state_directory
from odwolania2json.model import DEFAULT_CONFIG, load_classes
from odwolania2json.review import (config_digest, digest, inspect, journal_path, open_journal,
                                   read_report, report_path, save_decision)

STATIC = Path(__file__).with_name("static")
ASSETS = {"/": ("index.html", "text/html"), "/panel.css": ("panel.css", "text/css"),
          "/panel.js": ("panel.js", "text/javascript")}
MAX_REQUEST = 16_384
PDF_LOCK = Lock()


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
        return {**record, **view, "result": json.loads(raw) if raw else None, "raw_json": raw, "schema": schema}

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

    def get(self):
        address = self.request_address()
        if address.path in ASSETS:
            filename, content_type = ASSETS[address.path]
            self.send(HTTPStatus.OK, (STATIC / filename).read_bytes(), content_type)
            return
        panel = self.server.panel
        if address.path == "/api/documents":
            result = panel.documents()
        elif address.path in ("/api/document", "/api/page"):
            query = parse_qs(address.query, strict_parsing=True, max_num_fields=3)
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

    def post(self):
        address = self.request_address(write=True)
        if address.path != "/api/decision":
            raise PanelError(HTTPStatus.NOT_FOUND, "Nie ma takiej akcji panelu.")
        if self.headers.get_content_type() != "application/json":
            raise PanelError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Decyzja wymaga danych JSON.")
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= MAX_REQUEST:
            raise PanelError(HTTPStatus.BAD_REQUEST, "Nieprawidłowa długość danych decyzji.")
        payload = json.loads(self.rfile.read(size))
        if not isinstance(payload, dict):
            raise ValueError("Dane decyzji muszą być obiektem JSON.")
        json.dumps(payload, allow_nan=False)
        self.reply(HTTPStatus.OK, self.server.panel.decide(payload))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("input"), help="katalog PDF-ów")
    parser.add_argument("--output", type=Path, default=Path("output"), help="katalog surowych wyników")
    parser.add_argument("--diagnostics", type=Path, default=Path("diagnostics/last-run.json"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        panel = Panel(args.input, args.output, args.diagnostics, args.config)
        with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
            server.panel = panel
            print(f"Panel dostępny na http://127.0.0.1:{server.server_port}", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Błąd panelu: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
