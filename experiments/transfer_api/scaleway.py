"""Read one transfer field from a masked image via the Scaleway serverless API."""
import base64
import io
import os
import re
import stat
from http.client import HTTPException
from pathlib import Path
from time import perf_counter

from experiments.abc.adapters import MAX_RESPONSE_BYTES, PROVIDERS, encode, get_usage, https_post, sha256, strict_json
from odwolania2json.operations import DATE, normalize, normalize_date

PROVIDER = PROVIDERS["C"]
FIELD_INSTRUCTIONS = {
    "kwota": "Odczytaj kwotę głównej operacji jako liczbę bez znaku i spacji, z kropką i dwiema cyframi po niej. Pomiń opłaty i saldo.",
    "data_operacji": "Odczytaj datę operacji lub wykonania w formacie RRRR-MM-DD. Datę księgowania wybierz dopiero przy braku daty operacji. Pomiń datę wydruku.",
}
ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"wiersz": {"type": ["integer", "null"]}, "wartosc": {"type": ["string", "null"]}},
    "additionalProperties": False,
    "required": ["wiersz", "wartosc"],
}
SYSTEM = (
    "Odczytujesz jedno brakujące pole polskiego potwierdzenia przelewu. Obraz zawiera ponumerowane "
    "wycinki cyfr; liczba z lewej to numer wiersza, po prawej jest wartość. Etykiety są pomocnicze "
    "i mogą być niepełne. Zwróć numer wybranego wiersza i wartość odczytaną z obrazu. "
    "Gdy cyfry są nieczytelne lub wybór wartości niejednoznaczny, zwróć null w obu polach. "
    "Nie uzupełniaj cyfr z domysłu. Odpowiedz tylko obiektem JSON."
)


def load_token():
    token = os.environ.get(PROVIDER.token_env, "")
    if not token:
        path = Path.home() / ".config/odwolania2json/llm.env"
        if not path.is_file():
            raise ValueError("missing_key_file")
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), encoding="utf-8-sig") as file:
            st = os.fstat(file.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
                raise ValueError("private_key_file_permissions")
            for line in file:
                name, separator, value = line.partition("=")
                if separator and name.strip() == PROVIDER.token_env:
                    token = value.strip()
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        token = token[1:-1]
    if not token or any(ch.isspace() for ch in token) or not token.isascii():
        raise ValueError("missing_or_invalid_key")
    return token


def make_payload(field, png, rows):
    system = SYSTEM if field == "kwota" else (
        "Obraz zawiera numer wiersza, etykietę rodzaju daty i wycinek jej wartości. "
        "Polski miesiąc może być zapisany słownie. Odczytaj wyłącznie widoczną datę, bez zgadywania. "
        "Przy nieczytelnym dniu, miesiącu lub roku zwróć null w obu polach. Odpowiedz tylko obiektem JSON."
    )
    labels = "\n".join(f"{r['row']}: {', '.join(r['labels']) or 'brak etykiety'}" for r in rows)
    task = FIELD_INSTRUCTIONS[field] + "\nEtykiety kolejnych wierszy:\n" + labels
    image_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    return {
        "model": PROVIDER.model, "temperature": 0, "max_tokens": 96, "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [{"type": "text", "text": task},
                                         {"type": "image_url", "image_url": {"url": image_url}}]},
        ],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "odczyt_przelewu", "strict": True, "schema": ANSWER_SCHEMA,
        }},
    }


def parse_answer(obj, field, rows):
    if not isinstance(obj, dict) or set(obj) != {"wiersz", "wartosc"}:
        raise ValueError("invalid_answer_schema")
    row, value = obj["wiersz"], obj["wartosc"]
    if row is None and value is None:
        return None, None
    if type(row) is not int or row not in {r["row"] for r in rows} or not isinstance(value, str):
        raise ValueError("invalid_answer_evidence")
    if field == "kwota":
        if not re.fullmatch(r"(?:[0-9]{1,12}|[0-9]{1,3}(?: [0-9]{3}){1,3})[.,][0-9]{2}", value):
            raise ValueError("invalid_amount")
        return row, normalize(value, "money")
    parsed = normalize_date(value) if re.fullmatch(DATE, value, re.I) else None
    if parsed is None:
        raise ValueError("invalid_date")
    return row, parsed


def read_field(token, field, png, rows):
    body = encode(make_payload(field, png, rows))
    record = {"model": PROVIDER.model, "request_sha256": sha256(body), "http": None, "usage": None}
    started = perf_counter()
    try:
        response = https_post(PROVIDER.url, {"Content-Type": "application/json",
                                             "Authorization": "Bearer " + token}, body, 45)
        record["http"] = response.status
        if response.status != 200:
            record["outcome"] = f"http_{response.status}"
            return record
        if len(response.body) > MAX_RESPONSE_BYTES:
            raise ValueError("response_too_large")
        reply = strict_json(response.body)
        record["usage"] = get_usage(reply)
        record["returned_model"] = reply.get("model")
        choice, = reply["choices"]
        message = choice["message"]
        if choice["finish_reason"] != "stop" or message.get("refusal") or message.get("tool_calls"):
            raise ValueError("incomplete_or_filtered")
        record["answer_sha256"] = sha256(message["content"].encode("utf-8"))
        row, value = parse_answer(strict_json(message["content"]), field, rows)
        record.update(row=row, value=value, outcome="abstained" if row is None else "accepted")
    except (ValueError, KeyError, TypeError, RecursionError, AttributeError):
        record["outcome"] = "invalid_response"
    except (OSError, HTTPException):
        record["outcome"] = "transport_error"
    finally:
        record["transport_seconds"] = round(perf_counter() - started, 4)
    return record


def smoke(token):
    from PIL import Image, ImageDraw

    image = Image.new("L", (560, 156), 255)
    labels = ImageDraw.Draw(image)
    for y, row, digits in ((18, "1", "0,00"), (96, "2", "17,42")):
        labels.text((10, y), row, fill=0, font_size=30)
        labels.text((85, y), digits, fill=0, font_size=43)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    rec = read_field(token, "kwota", stream.getvalue(), [
        {"row": 1, "labels": ["oplata", "PLN"]},
        {"row": 2, "labels": ["kwota", "PLN"]},
    ])
    rec["synthetic_only"] = True
    rec["valid"] = rec.get("row") == 2 and rec.get("value") == 17.42
    return rec
