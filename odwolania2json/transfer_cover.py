"""Recognize a standalone completed transfer behind a neutral opening."""
import re

from .bank_scan import view_evidence
from .model import FLAGS, class_candidate
from .transfer import ROLE, ROLES, page_lines

COVER = re.compile(
    r"(?:(?:karta techniczna|strona tytu[łl]owa|ok[łl]adka(?: dokumentu| skanu)?)"
    r"(?:[ \t]+[-–—][ \t]+\w{1,25})?|(?:metryka|metadane|oznaczenie) (?:skanu|digitalizacji)|"
    r"skan dokumentu|strona (?:separuj[ąa]ca|archiwalna)|karta archiwizacji)", re.I,
)
PAGINATION = re.compile(
    r"(?:(?:\w+[ \t]+)?(?:dane|wydruk|metryka|wersja|kopia|identyfikator)\b[\w ,\-]{0,35}\.[ \t]+)?"
    r"(?:strona|str\.|arkusz|karta)[ \t]+0?1[ \t]*(?:z|/)[ \t]*0?2\.?", re.I,
)
COVER_METADATA = re.compile(
    r"(?:(?:identyfikator|numer|nr\.?|wersja) (?:skanu|pliku|pakietu)[ \t]*:[ \t]*"
    r"[a-z0-9][a-z0-9._/-]{0,31}|(?:format|format pliku|format skanu)[ \t]*:[ \t]*(?:pdf(?:/a)?|tiff?|png|jpe?g)|"
    r"data (?:skanowania|digitalizacji)[ \t]*:[ \t]*[0-9]{4}-[0-9]{2}-[0-9]{2}|0?1[ \t]*/[ \t]*0?2)", re.I,
)
COVER_CONTENT = re.compile(
    r"\b(?:(?:odwo[łl]|pe[łl]nomoc|faktur|p[łl]atno|przelew|potwierdz|za[łl][ąa]cz|o[śs]wiadcz|"
    r"wnios|wnos|wezw|skarg|umow|protok|instruk|wz[oó]r|przyk[łl]ad|przetarg|wp[łl]at|rachun|kwot|"
    r"nadaw|odbior|sygnatur|wyrok|decyz|pism|wykonaw|zamaw|podpis|zlecen)\w*|tytu[łl](?:em|u)?)\b", re.I,
)
RECEIPT = re.compile(
    r"^[ \t]*(?:(?:potwierdzenie|dow[óo]d)(?: (?:realizacji|wykonania|zaksi[ęe]gowania))?"
    r" przelewu(?: krajowego)?|(?:bank transfer|transfer) confirmation)[ \t]*$", FLAGS,
)
INCOMPATIBLE = re.compile(
    r"^[ \t]*(?:instrukcj\w*|poradnik|podr[ęe]cznik|wz[oó]r|szablon|przyk[łl]ad\w*|"
    r"(?:poni[żz]ej|ni[żz]ej)[ \t]+(?:przyk[łl]ad|cytat)\w*|"
    r"wyci[ąa]g|zestawienie operacji|dane do zwrotu|pismo przewodnie|instruction\w*|sample|example|"
    r"data (?:planowana|przewidywana)|(?:planowana|przewidywana) data|"
    r"(?:(?:stan|status)(?: (?:operacji|transakcji|przelewu))?|transaction status)"
    r"[ \t:|]*(?:\n[ \t]*)?(?:do (?:realizacji|autoryzacji|podpisu)|oczekuj\w*|"
    r"anulowan\w*|odrzucon\w*|niezrealizowan\w*|niewykonan\w*|zaplanowan\w*|"
    r"pending|cancelled|canceled|rejected|scheduled))\b", FLAGS,
)
REQUIRED_SIGNALS = (
    "nagłówek_przelewu", "zaksięgowany_przelew", "rola_rachunku", "kwota_operacji", "data_operacji",
)


def neutral_cover(text):
    if len(text) > 320 or COVER_CONTENT.search(text):
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    # A separator or explicit pagination establishes the role. Every other line must be metadata.
    has_marker = False
    for line in lines:
        if COVER.fullmatch(line) or PAGINATION.fullmatch(line):
            has_marker = True
        elif not COVER_METADATA.fullmatch(line):
            return False
    return has_marker



def completed_transfer(document, config):
    if len(document.starts) != 2 or config.get("builder") != "transfer":
        return None
    if document.scan_quality and document.scan_quality["page_count"] != 2:
        return None
    offset = document.starts[1][0]
    page = document.text[offset:].removesuffix("\n\f\n")
    headings = list(RECEIPT.finditer(page))
    if "\f" in page or len(headings) != 1 or headings[0].start() >= 400 or INCOMPATIBLE.search(page):
        return None
    rows = tuple(line for _, line in page_lines(page, offset))
    roles = {match.lastgroup for line in rows if (match := ROLE.match(line))}
    if roles != ROLES.keys():
        return None
    numbers = view_evidence(rows)
    if not all(unique_labelled_value(numbers.get(key, ())) for key in ("kwota", "data_operacji")):
        return None
    return class_candidate(document, "przelew", config, page, offset, REQUIRED_SIGNALS)


def unique_labelled_value(readings):
    priority = max((rank for rank, _ in readings), default=0)
    return priority >= 2 and len({value for rank, value in readings if rank == priority}) == 1
