"""Extract procedural fields from explicit evidence in an appeal."""

import re

from .model import FLAGS
from .operations import DATE, MONTHS, normalize


FILING = re.compile(
    r"\bwnosz(?:ę|imy)[ \t\n]+(?:(?:niniejsze|niniejszym)[ \t\n]+)?"
    r"odwołanie[ \t\n]+(?:od|wobec|na)\b", FLAGS,
)
FILING_TITLE = re.compile(
    r"\A\s*od\s+czynności(?:\s+(?:i|lub|oraz)\s+zaniechań)?\s+Zamawiającego\s+wobec(?=\s*:)", FLAGS,
)
FOREIGN_START = (
    r"^[ \t]*(?:cytat|przytoczenie|treść[ \t]+cytatu|"
    r"(?:przytoczenie|treść)[ \t]+(?:cytowanego|przytoczonego)[ \t]+"
    r"(?:odwołania|pisma|wypowiedzi|oświadczenia)"
    r"(?:[ \t]+(?:innego[ \t]+wykonawcy|zamawiającego|przystępującego|pełnomocnika))?)\s*:"
    r"|^[ \t]*(?:inny[ \t]+wykonawca|zamawiający)[ \t]+(?:napisał|wskazał|oświadczył)[ \t]*:"
)
FOREIGN = re.compile(
    rf"(?P<open>{FOREIGN_START})|^[ \t]*(?:koniec[ \t]+(?:cytatu|przytoczenia)|"
    r"własne[ \t]+stanowisko|stanowisko[ \t]+własne)[.:\t ]*$", FLAGS,
)
QUOTED = re.compile(r'„[^”\f]*”|«[^»\f]*»|"[^"\n\f]*"')
ZONE_END = re.compile(r"^[ \t]*(?:[IVX]+[.)][ \t]+)?(?:uzasadnienie|wnioski końcowe)\b", FLAGS)
SECTION_END = re.compile(
    r"^[ \t]*(?:[IVX]+[.)][ \t]+)?(?:uzasadnienie|żądania|wnioski końcowe|petitum|"
    r"podstawy prawne|zarzuty|termin składania)\b"
    r"|\b(?:wnosz(?:ę|imy)\s+o|żądam(?:y)?|domagam(?:y)?\s+się|"
    rf"zarzuc(?:am(?:y)?|a|ają)|wobec\s+powyższego)\b|{FOREIGN_START}", FLAGS,
)
LIST_ITEM = re.compile(r"(?:^[ \t]*|(?<=:)[ \t]*)(?P<number>\(?\d{1,2}|[IVX]+|[a-d])[.)][ \t]+", FLAGS)
FIRST_ITEM = {"1", "(1", "i", "a"}
MARKED_LIST = re.compile(r"\A\s*:|(?:następując\w*|czynnoś\w*|zaniechani\w*)[^;]*:\s*\Z", FLAGS)
STAMP = re.compile(rf"(?<!\d)(?P<date>{DATE})(?!\d)", FLAGS)
# A dot detached from the previous word is common OCR noise in names.
LIST_CLAUSE_END = re.compile(r";|(?<!\s)\.(?=[ \t]+(?-i:[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]{2,})|\s*\Z)", FLAGS)
# OCR sometimes reads the second half of a date above the line containing its day.
WRAPPED_STAMP = re.compile(
    rf"^[ \t]*(?P<month>{'|'.join(MONTHS)})[ \t]+(?P<year>20\d{{2}})"
    r"(?:[ \t]+(?:r\.|roku))?[ \t]*[;.]?[ \t]*\n(?:[ \t]*\n)?"
    r"[ \t]*(?:\w+[ \t]+){0,2}w[ \t]+dniu[ \t]+(?P<day>\d{1,2})[ \t]*(?:\n[ \t]*)*\Z", FLAGS,
)
CUES = re.compile(
    r"(?P<other>\b(?:wniesieni\w*\s+odwołani\w*|termin\w*|wydrukow\w*|data\s+wydruku|"
    r"ustaw\w*|rozporządzeni\w*|ogłoszeni\w*\s+o\s+zamówieni\w*|w\s+postępowani\w*\s+z\s+ogłoszeni\w*)\b)"
    r"|(?P<notice>\b(?:o\s+(?:której|którym|których|czym)\s+)?"
    r"(?:zamawiający\s+)?(?:poinformow\w*|zawiadomi\w*|powiadomi\w*|"
    r"przekaza\w*\s+informacj\w*|otrzyma\w*(?:[ \t]+\w+){0,2}[ \t]+wiadomoś[ćc]|wiadomoś[ćc])\b)"
    r"|(?P<act>\b(?:odrzuc\w*|wyklucz\w*|wybor\w*|wybór|unieważn\w*|"
    r"opublikowa\w*|publikacj\w*|modyfikacj\w*|zmodyfikow\w*|wyjaśni\w*|"
    r"zaniechani\w*|dokonani\w*\s+czynnoś\w*)\b)", FLAGS,
)
DATE_JOIN = re.compile(r"(?:\bz[ \t]+(?:dnia[ \t]+)?|\bw[ \t\n]+dniu[ \t]+|\bdnia[ \t]+)\s*\Z", FLAGS)
DEADLINE_JOIN = re.compile(r"\b(?:do|od)[ \t]+(?:dnia[ \t]+)?\s*\Z", FLAGS)
UNRELATED_PUBLICATION = re.compile(
    r"\bw[ \t\n]+postępowani\w*[ \t\n]+(?:z[ \t\n]+)?(?:ogłoszeni\w*|wszczęt\w*)\b", FLAGS,
)
OTHER_NOTICE = re.compile(r"\b(?:o|na\s+temat)\s+(?:termin\w*|ogłoszeni\w*|publikacj\w*)\b", FLAGS)

REFERENCE = re.compile(
    r"^[ \t]*(?:postępowanie[ \t]+(?:nr\.?|numer)|(?:nr\.?|numer|znak)[ \t]+postępowania)"
    r"[ \t]*[:,.]?[ \t]*(?P<value>(?=[A-Z0-9./_-]*[0-9])[A-Z0-9][A-Z0-9./_-]{2,})"
    r"(?=[ \t,;)\n\f]|$)", FLAGS,
)
JOURNAL = re.compile(
    r"\bogłoszeni\w*[ \t\n]+w[ \t\n]+Dzienniku[ \t\n]+Urzędowym[ \t\n]+Unii[ \t\n]+"
    r"Europejskiej[ \t\n]+(?:nr\.?|numer)[ \t\n]+(?P<year>20\d{2})[ \t]*/[ \t]*"
    r"[S58]\d?[ \t\n]+[0-9]{1,3}[ \t]*[-–][ \t]*(?P<value>[0-9]{6})(?![0-9/-])", FLAGS,
)
UNPAIRED_TITLE = re.compile(
    r"\b(?:pn\.|pod[ \t]+nazwą)[ \t\n]+(?P<value>(?![„“\"])[^\W\d_][^„“”\"\f]{3,299})"
    r"[”\"][ \t]*,?[ \t\n]+(?:nr|numer|znak)[ \t]+(?:referencyjny|postępowania)\b", FLAGS,
)


def filing_scope(text, *, titled=False):
    zone = ZONE_END.search(text)
    if zone:
        text = text[:zone.start()]
    quotes = list(QUOTED.finditer(text))
    boundaries = list(FOREIGN.finditer(text))
    declaration = FILING_TITLE.match(text) if titled else None
    for mark in FILING.finditer(text) if declaration is None else ():
        if any(quote.start() <= mark.start() < quote.end() for quote in quotes):
            continue
        prior = next((boundary for boundary in reversed(boundaries) if boundary.start() < mark.start()), None)
        if prior is None or not prior["open"]:
            declaration = mark
            break
    if declaration is None:
        return "", 0

    start = declaration.end()
    scope = text[start:start + 1600]
    boundary = SECTION_END.search(scope)
    if boundary:
        scope = scope[:boundary.start()]
    marker = LIST_ITEM.search(scope)
    if marker:
        if not MARKED_LIST.search(scope[:marker.start()]):
            return scope[:marker.start()], start
        if marker["number"].casefold() not in FIRST_ITEM:
            return "", start
        start += marker.end()
        scope = scope[marker.end():]
        second = LIST_ITEM.search(scope)
        if second:
            scope = scope[:second.start()]
    return scope, start


def wrapped_date(text):
    stamp = WRAPPED_STAMP.search(text)
    if stamp is None or not any(cue.lastgroup == "act" for cue in CUES.finditer(text[:stamp.start()])):
        return None
    value = normalize(f"{stamp['day']} {stamp['month']} {stamp['year']}", "date")
    return (value, stamp.start("month"), "data_czynności_odczytana_z_dwóch_wierszy") if value else None


def dated_act(text):
    candidates = ({}, {})
    action_seen = False
    tag = None
    clause_end = LIST_CLAUSE_END.search(text)
    end = clause_end.start() if clause_end else len(text)
    unrelated = UNRELATED_PUBLICATION.search(text, 0, end)
    scope = text[:unrelated.start() if unrelated else end]
    cues = iter(CUES.finditer(scope))
    next_cue = next(cues, None)
    for stamp in STAMP.finditer(scope):
        while next_cue and next_cue.end() <= stamp.start():
            tag = next_cue
            action_seen |= tag.lastgroup == "act"
            next_cue = next(cues, None)
        if not action_seen or tag is None or tag.lastgroup == "other":
            continue
        tail = scope[tag.end():stamp.start()]
        if len(tail) > 130 or re.search(r"[\f]|[\n][ \t]*\n", tail) or DEADLINE_JOIN.search(tail):
            continue
        if tag.lastgroup == "act" and not DATE_JOIN.search(tail):
            continue
        if tag.lastgroup == "notice" and OTHER_NOTICE.search(tail):
            continue
        value = normalize(stamp["date"], "date")
        if value is not None:
            candidates[int(tag.lastgroup == "notice")].setdefault(value, stamp.start("date"))
    rules = ("data_czynności_we_wniesieniu", "data_powiadomienia_o_zaskarżonej_czynności")
    for options, rule in zip(candidates, rules):
        if options:
            if len(options) != 1:
                return None
            value, offset = next(iter(options.items()))
            return value, offset, rule
    if unrelated is None and not STAMP.search(scope):
        return wrapped_date(text)
    return None


def add_filing_date(result, body, *, titled=False):
    appeal = result.data["OdwolanieKIO"]
    if appeal["czynnosc_dzien"] is not None:
        return
    scope, start = filing_scope(body.text, titled=titled)
    found = dated_act(scope)
    if found:
        value, offset, rule = found
        if appeal["data"] is None or value <= appeal["data"]:
            result.put(("OdwolanieKIO", "czynnosc_dzien"), value, body.offset + start + offset, rule)


def add_procedure_fields(result, cover):
    definitions = (
        ("numer_postepowania", REFERENCE, "identifier", "oznaczenie_postępowania_w_nagłówku"),
        ("numer_ted", JOURNAL, "text", "numer_publikacji_w_dzienniku_urzędowym_ue"),
        ("tytul", UNPAIRED_TITLE, "text", "tytuł_przed_numerem_referencyjnym"),
    )
    procedure = result.data["ZamowieniePubliczne"]
    for name, pattern, operation, rule in definitions:
        if procedure[name] is not None:
            continue
        candidates = {}
        for match in pattern.finditer(cover.text):
            value = normalize(match["value"], operation)
            if value:
                if name == "numer_ted":
                    value = f"{value}-{match['year']}"
                candidates.setdefault(value, match.start("value"))
        if len(candidates) == 1:
            value, offset = next(iter(candidates.items()))
            result.put(("ZamowieniePubliczne", name), value, cover.offset + offset, rule)
