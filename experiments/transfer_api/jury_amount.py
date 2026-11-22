"""Uzupełnij wyłącznie pustą kwotę rozpoznanego przelewu z wycinka cyfr."""
import json
import logging
from pathlib import Path
import sqlite3
import subprocess
import sys
from contextlib import closing
from time import monotonic


KEY_FILE = Path("/run/odwolania2json/scaleway.env")
LEDGER = Path("/work/llm/usage.sqlite3")
# 20 x 0,05 EUR. Rezerwacja obejmuje pełny kontekst 128k i 96 tokenów
# odpowiedzi. Każda wysłana próba zużywa miejsce również po błędzie.
MAX_REQUESTS = 20
MAX_EXTRA_SECONDS = 75
FIELD = "przelew_bankowy.kwota"


class AmountReader:
    def __init__(self, tessdata):
        self.tessdata = tessdata
        self.extra_seconds = 0.0
        self.unavailable = False

    def claim(self, key, *, reserve):
        # Commit rezerwacji poprzedza połączenie z dostawcą. Restart,
        # powtórzenie partii i równoległy panel korzystają z tej samej tabeli.
        with closing(sqlite3.connect(LEDGER, timeout=2)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS calls (pdf TEXT PRIMARY KEY, result TEXT)")
            row = db.execute("SELECT result FROM calls WHERE pdf=?", (key,)).fetchone()
            if row is not None:
                return "seen", json.loads(row[0]) if row[0] else None
            if db.execute("SELECT count(*) FROM calls").fetchone()[0] >= MAX_REQUESTS:
                return "full", None
            if reserve:
                db.execute("INSERT INTO calls(pdf) VALUES(?)", (key,))
            return "free", None

    def get_amount(self, pdf, key):
        state, saved = self.claim(key, reserve=False)
        if state != "free":
            return saved
        if self.unavailable or self.extra_seconds >= MAX_EXTRA_SECONDS:
            return None
        from .crops import numeric_panel
        from .scaleway import PROVIDER, load_token, read_field

        token = load_token(KEY_FILE)
        panel, rows = numeric_panel(pdf, "kwota", self.tessdata)
        if not panel or not rows:
            return None
        primary = {"kwota", "wartosc", "amount"}
        excluded = {"oplata", "prowizja", "saldo"}
        allowed = {r["row"]: r for r in rows if not excluded.intersection(r["labels"])
                   and (primary.intersection(r["labels"]) or len(rows) == 1 and "PLN" in r["labels"])}
        if not allowed:
            return None
        state, saved = self.claim(key, reserve=True)
        if state != "free":
            return saved
        reply = read_field(token, "kwota", panel, rows, timeout=10)
        if reply.get("http") in (401, 402, 403, 429) or reply["outcome"] == "transport_error":
            self.unavailable = True
        if reply["outcome"] != "accepted" or reply.get("row") not in allowed:
            return None
        row = allowed[reply["row"]]
        result = {"amount": reply["value"], "evidence": {
            "page": row["page"], "box": row["box"], "render_scale": row["render_scale"],
            "rule": "scaleway_numeric_crop", "source": "llm", "precision": "page",
            "model": PROVIDER.model,
        }}
        with closing(sqlite3.connect(LEDGER, timeout=2)) as db, db:
            db.execute("UPDATE calls SET result=? WHERE pdf=?", (json.dumps(result), key))
        return result

    def fill(self, pdf, pdf_hash, value, record):
        if (record.get("class") != "przelew" or record.get("status") != "ok"
                or 1 not in record.get("ocr_pages", ()) or not isinstance(value, dict)):
            return
        transfer = value.get("przelew_bankowy")
        if not isinstance(transfer, dict) or "kwota" not in transfer or transfer["kwota"] is not None:
            return
        started = monotonic()
        try:
            state, result = self.claim(pdf_hash, reserve=False)
            if state == "free" and not self.unavailable and self.extra_seconds < MAX_EXTRA_SECONDS:
                # Oddziel proces natywnych bibliotek OCR i limit czasu od głównej partii.
                worker = subprocess.run(
                    [sys.executable, "-B", "-m", "experiments.transfer_api.jury_amount",
                     str(self.tessdata), str(pdf), pdf_hash],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    timeout=18, check=True,
                )
                response = json.loads(worker.stdout)
                self.unavailable = response["unavailable"]
                result = response["result"]
            if result is not None:
                transfer["kwota"] = result["amount"]
                record["fields"][FIELD] = result["evidence"]
        except Exception as exc:
            # Opcjonalny dostawca, zapis budżetu lub parser wycinka nie mogą
            # przerwać ekstrakcji innych PDF-ów. Nie loguj danych klienta.
            logging.warning("Scaleway: utrzymano lokalny wynik (%s)", type(exc).__name__)
            self.unavailable = True
        finally:
            self.extra_seconds += monotonic() - started


if __name__ == "__main__":
    tessdata, source, digest = sys.argv[1:]
    reader = AmountReader(Path(tessdata))
    amount = reader.get_amount(Path(source), digest)
    print(json.dumps({"result": amount, "unavailable": reader.unavailable}))
