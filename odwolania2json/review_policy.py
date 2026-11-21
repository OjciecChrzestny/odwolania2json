"""Deterministyczna polityka kontroli dla diagnostyki operacyjnej."""

from collections.abc import Mapping

from .bank_accounts import PAYEE, PAYER, valid_nrb

TRANSFER = "przelew_bankowy"
ACCOUNTS = {f"{TRANSFER}.{role}": role for role in (PAYER, PAYEE)}
PROFILE_CLASSES = frozenset({"przelew", "odwolanie", "pelnomocnictwo", "negative"})
PAGE_CODES = {
    "partial": "page_partial",
    "unreadable": "page_unreadable",
    "unassessed": "page_unassessed",
}


def _page_number(value):
    return type(value) is int and value > 0


def _has_value(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (Mapping, list)):
        return bool(value)
    return value is not None


def _leaves(value, prefix=""):
    if isinstance(value, Mapping):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            yield from _leaves(item, path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaves(item, f"{prefix}.{index}")
    else:
        yield prefix, value


def _required_paths(document_class, value, leaves):
    if document_class == "przelew":
        return {
            f"{TRANSFER}.{key}" for key in ("data_operacji", "kwota", "tytul", PAYER, PAYEE)
        }
    if document_class == "odwolanie":
        required = {"OdwolanieKIO.czynnosc_powod_id", "OdwolanieKIO.czynnosc_opis"}
        for role in ("Odwolujacy", "Zamawiajacy"):
            parties = value.get(role)
            if not isinstance(parties, list) or not parties:
                required.add(role)
            else:
                required.update(f"{role}.{index}.nazwa" for index in range(len(parties)))
        return required

    required = set()
    for role in ("mocodawca", "pelnomocnicy"):
        parties = value.get(role)
        if not isinstance(parties, list) or not parties:
            required.add(role)
            continue
        for index, party in enumerate(parties):
            path = f"{role}.{index}"
            if role == "pelnomocnicy":
                required.add(f"{path}.imie_nazwisko")
                continue
            kind = leaves.get(f"{path}.data.typ")
            required.add(f"{path}.data.typ")
            name = "imie_nazwisko" if kind == "osoba_fizyczna" else "nazwa"
            required.add(f"{path}.data.{name}")
            signers = party.get("podpisujacy") if isinstance(party, Mapping) else None
            if isinstance(signers, list):
                required.update(f"{path}.podpisujacy.{i}.imie_nazwisko"
                                for i in range(len(signers)))
    return required


def _evidence_rows(raw):
    if isinstance(raw, Mapping):
        return (raw,)
    return tuple(row for row in raw or () if isinstance(row, Mapping))


def _precise(row, readable):
    if not _page_number(row.get("page")) or row["page"] not in readable:
        return False
    if not _has_value(row.get("rule")) or row.get("source") not in ("text", "ocr"):
        return False
    precision = row.get("precision")
    if precision == "snippet":
        snippet = row.get("snippet")
        return isinstance(snippet, str) and bool(snippet.strip())
    return precision == "region" and isinstance(row.get("region"), Mapping) and bool(row["region"])


def _conflicting_values(rows, value):
    support = [row for row in rows if row.get("kind", "support") == "support"]
    claims = [row["value"] for row in support if _has_value(row.get("value"))]
    if _has_value(value):
        claims.append(value)
    if any(row.get("kind") == "conflict" for row in rows):
        return True
    if (claims or support) and any(row.get("kind") == "absent" for row in rows):
        return True
    return bool(claims) and any(claim != claims[0] for claim in claims[1:])


def _field_problem(path, value, rows, readable, required):
    role = ACCOUNTS.get(path)
    if _conflicting_values(rows, value) or (
        role and any(row.get("role") not in (None, role) for row in rows)
    ):
        return "account_role_conflict" if role else "field_evidence_conflict"
    if not _has_value(value):
        if required:
            return "missing_required_value"
        if value is None and any(row.get("kind") == "absent" and _has_value(row.get("reason"))
                                 and _precise(row, readable) for row in rows):
            return None
        return "optional_absence_unconfirmed"
    if role and not valid_nrb(value):
        return "invalid_account_checksum"
    support = [row for row in rows if row.get("kind", "support") == "support"
               and _precise(row, readable)]
    if role and not any(row.get("role") == role for row in support):
        return "account_role_unconfirmed"
    if not support:
        return "field_evidence_insufficient"
    return None


def decide_review(document_class, *, pages=(), fields=None, value=None,
                  negative_evidence=(), classification_conflicts=(), verified_profiles=()):
    """Zwróć klucze status, profile i reasons gotowe do zapisu w JSON.

    Klasa jest zgodna z diagnostyką ekstraktora. Strony modułu 02 mają klucze
    page i status. fields mapuje kropkowane ścieżki Extraction.put na rekord
    dowodu lub listę rekordów. Rekord zawiera page, rule, source i precision.
    Dokładny dowód wskazuje snippet albo region. value to wynik przechodzący
    walidację schematu ekstraktora. Dla sprzecznych obserwacji zachowaj
    value w rekordzie dowodu (znormalizowaną wartość) albo
    kind="conflict". Dowód roli rachunku ma role równą z_rachunku lub
    na_rachunek. Dowód braku ma kind="absent" i obserwowalny reason.
    negative_evidence wyklucza klasy docelowe dla całego dokumentu i wskazuje
    czytelną stronę. Brak trafienia klasyfikatora nie stanowi takiego dowodu.
    classification_conflicts zawiera numery stron sprzecznych sygnałów klas.

    verified_profiles domyślnie jest puste. Nazwę klasy jako profil może
    włączyć koordynator po niezależnym pomiarze. Wynik ma wyłącznie blokujące
    reasons. Pole i stronę podajemy, jeśli można je wskazać z obserwacji.
    """
    if document_class == "read_error":
        return {"status": "review_required", "profile": document_class,
                "reasons": [{"code": "read_error"}]}

    reasons = set()
    known_pages, readable = set(), set()
    for observation in pages or ():
        page = observation.get("page")
        if not _page_number(page):
            reasons.add(("page_observations_invalid", "", 0))
            continue
        if page in known_pages:
            reasons.add(("page_observations_invalid", "", page))
        known_pages.add(page)
        status = observation.get("status")
        if status == "readable":
            readable.add(page)
        else:
            reasons.add((PAGE_CODES.get(status, "page_observations_invalid"), "", page))
    if sorted(known_pages) != list(range(1, len(known_pages) + 1)) or not known_pages:
        reasons.add(("page_observations_incomplete", "", 0))

    for page in classification_conflicts:
        reasons.add(("classification_conflict", "", page if _page_number(page) else 0))

    def add_field_reason(code, path, rows):
        locations = {row["page"] for row in rows
                     if _page_number(row.get("page")) and row["page"] in known_pages}
        reasons.update((code, path, page) for page in locations or {0})

    if document_class not in PROFILE_CLASSES:
        reasons.add(("unknown_profile", "", 0))
    elif document_class == "negative":
        negative_rows = _evidence_rows(negative_evidence)
        conflicting = [row for row in negative_rows if row.get("kind") == "conflict"]
        if conflicting:
            add_field_reason("classification_conflict", "", conflicting)
        if not any(row.get("kind", "support") == "support" and _precise(row, readable)
                   for row in negative_rows):
            add_field_reason("uncertain_negative", "", negative_rows)
        if value is not None:
            reasons.add(("unexpected_negative_value", "", 0))
    else:
        value = value if isinstance(value, Mapping) else {}
        fields = fields or {}
        leaves = dict(_leaves(value))
        required = _required_paths(document_class, value, leaves)
        for path in leaves.keys() | required | fields.keys():
            rows = _evidence_rows(fields.get(path))
            code = _field_problem(path, leaves.get(path), rows, readable, path in required)
            if code:
                add_field_reason(code, path, rows)
        payer, payee = (leaves.get(f"{TRANSFER}.{role}") for role in (PAYER, PAYEE))
        if document_class == "przelew" and _has_value(payer) and payer == payee:
            for path in ACCOUNTS:
                add_field_reason("account_role_conflict", path, _evidence_rows(fields.get(path)))

    if document_class in PROFILE_CLASSES and document_class not in verified_profiles:
        reasons.add(("profile_not_verified", "", 0))

    return {
        "status": "review_required" if reasons else "auto_accepted",
        "profile": document_class,
        "reasons": [
            {"code": code, **({"field": path} if path else {}), **({"page": page} if page else {})}
            for code, path, page in sorted(reasons)
        ],
    }
