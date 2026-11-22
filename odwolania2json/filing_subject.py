"""Recover a documented subject when the appeal has no selected action."""
from dataclasses import dataclass
import re

from .filing_reason import FILING_RULE, FOREIGN_START
from .legal import Fragment
from .model import FLAGS


SPACE = r"[ \t\n]+"
FULL_SPECIFICATION = rf"specyfikacji{SPACE}warunków{SPACE}zamówienia"
PUBLISHED_SPECIFICATION = (rf"{SPACE}{FULL_SPECIFICATION}(?:[ \t]*\(SWZ\))?"
                           rf"{SPACE}(?:opublikowanej|ogłoszonej|udostępnionej)\b")
SUBJECTS = (
    (4, r"treści" + PUBLISHED_SPECIFICATION),
    (5, rf"(?:modyfikacji|zmiany){SPACE}(?:treści{SPACE})?(?:SWZ\b|{FULL_SPECIFICATION}\b)"),
    (12, rf"(?:projektowanych{SPACE}postanowień|projektowanego{SPACE}postanowienia){SPACE}umowy\b"),
)
TITLE_LIST = re.compile(
    r"\A[ \t\n]*od[ \t]+czynności(?:[ \t]+i[ \t]+zaniechań)?[ \t]+zamawiającego[ \t.:]*\n"
    r"[ \t\n]*wobec[ \t]*:[ \t.]*\n[ \t\n]*(?:1[.)]|I[.)])[ \t]+",
    FLAGS,
)
FOREIGN_PROSE = (
    r"^[ \t]*z[ \t]+(?:pisma|odwołania|odpowiedzi)[ \t]+(?:innego[ \t]+wykonawcy|zamawiającego|przystępującego)"
    r"[ \t]+(?:przytaczam(?:y)?|cytuję|cytujemy)\b"
)
BORROWED = re.compile(
    r"^[ \t]*(?:cytat|przytoczenie|treść[ \t]+przytoczonego|pouczenie|uzasadnienie|żądania|wnioski końcowe)\b"
    r"|" + FOREIGN_PROSE, FLAGS,
)
CLOSED_QUOTES = re.compile(r"""(?:[^„“«"\f]|„[^”\f]*”|“[^”\f]*”|«[^»\f]*»|"[^"\f]*")*""")


REPRESENTATIVE = (
    r"(?:działając[ \t]+w[ \t]+imieniu[ \t]+"
    r"(?:(?!\b(?:nie|planuję|planujemy|zamierzam|zamierzamy)\b)[^\n\f,;:„“«\"]){1,100}?"
    r"[ \t]*,?" + SPACE + r")?"
)
OWN_OPENING = re.compile(
    r"[ \t]*(?:odwołując[ya][ \t]+zaskarża\b"
    r"|(?P<subject>przedmiotem[ \t]+niniejszego[ \t]+odwołania[ \t]+(?:jest|są)\b)"
    r"|" + REPRESENTATIVE + r"(?:składam|składamy)" + SPACE
    + r"(?:niniejsze" + SPACE + r")?odwołanie" + SPACE + r"(?:od|wobec|na)\b)" + SPACE,
    FLAGS,
)
OPENING_END = re.compile(
    r"^[ \t]*(?:[IVX]+[.)][ \t]+)?(?:uzasadnienie|żądania|petitum|wnioski końcowe|"
    r"podstawy prawne|zarzut|zarzuty)\b", FLAGS,
)
DECISION_PREFIX = re.compile(r"\A(?:decyzj[aeęi](?:[ \t]+zamawiającego)?[ \t]+o" + SPACE + ")", FLAGS)
ACTOR = r"(?:wykonawc\w*|odwołując\w*|konkurent\w*)\b"
OMISSION = r"zaniechan\w*" + SPACE + r"(?:czynności" + SPACE + r")?"
EXCLUDED_ACTOR = re.compile(r"wyklucz\w*" + SPACE + ACTOR, FLAGS)
CONTEXTUAL_SUBJECTS = {
    6: re.compile(r"(?:udziel\w*" + SPACE + r")?(?:odpowiedz\w*|wyjaśn\w*)" + SPACE
                  + r"(?:do" + SPACE + r")?(?:treści" + SPACE + r")?(?:SWZ|"
                  + FULL_SPECIFICATION + r")\b", FLAGS),
    7: re.compile(OMISSION + r"odrzuc\w*" + SPACE + r"ofert\w*\b", FLAGS),
    8: re.compile(OMISSION + r"wyklucz\w*" + SPACE + ACTOR, FLAGS),
    10: re.compile(OMISSION + r"unieważn\w*" + SPACE + r"postępowani\w*\b", FLAGS),
}
OPENING_ADDRESS = re.compile(
    r"\A[ \t\n]*(?:do[ \t]+)?(?:prezes(?:a)?[ \t]+)?"
    r"(?:KIO|krajow(?:a|ej)[ \t]+izb(?:a|y)[ \t]+odwoławcz(?:a|ej))[ \t]*:?[ \t]*$", FLAGS,
)
OPENING_APPELLANT = re.compile(r"^[ \t]*odwołując[ya][ \t]*:[ \t]*\S", FLAGS)
DRAFT = re.compile(
    r"\b(?:projekt[ \t]+(?:odwołania|pisma)|wersj[^\W\d_]*[ \t]+robocz[^\W\d_]*|"
    r"(?:wzór|szablon)[ \t]+(?:odwołania|pisma)|do[ \t]+(?:akceptacji|uzgodnienia))\b",
    FLAGS,
)
QUOTE_OPENING = re.compile(FOREIGN_START.removeprefix("^"), FLAGS)
QUOTE_CLOSING = re.compile(
    r"^[ \t]*koniec[ \t]+(?:cytatu|przytoczenia)[ \t]*[.:]?[ \t]*$", FLAGS,
)
OPENING_GAP = re.compile(r"[ \t\n\f]*")
CLAUSE_END = r'[;:!?„“«"\f]|\.(?=\s|$)|^[ \t]*(?:\d+[.)]|[-•])'


@dataclass(frozen=True)
class FilingSubject:
    reason_id: int
    description: str
    page: int
    offset: int
    end: int
    rule: str


def _title_list(document, config):
    first_page = document.text.split("\f", 1)[0]
    heading = re.search(config["patterns"]["header"], first_page[:2400], FLAGS)
    if not heading:
        return None
    before = first_page[:heading.start()]
    if BORROWED.search(before) or not CLOSED_QUOTES.fullmatch(before):
        return None
    items = TITLE_LIST.match(first_page[heading.end():])
    if items is None:
        return None
    offset = heading.end() + items.end()
    return Fragment(first_page[offset:], offset)


def select_filing_subject(document, config, declaration=None, *, nominative=False):
    """Use a screened own declaration, or an opening title's explicitly introduced first item."""
    clause = declaration if declaration is not None else _title_list(document, config)
    if clause is None:
        return None
    clause = clause.stripped()
    if not clause.text or not 0 <= clause.offset < len(document.text):
        return None
    if not document.text.startswith(clause.text, clause.offset):
        return None

    for reason_id, pattern in SUBJECTS:
        if reason_id == 4 and nominative:
            pattern = r"treść" + PUBLISHED_SPECIFICATION
        match = re.match(pattern, clause.text, FLAGS)
        if match is None:
            continue
        end = clause.offset + match.end()
        page = document.page(clause.offset)
        if document.page(end - 1) != page:
            return None
        description = config["reasons"]["descriptions"][str(reason_id)]
        rule = "przedmiot_pierwszej_zaskarżonej_czynności"
        return FilingSubject(reason_id, description, page, clause.offset, end, rule)
    return None


def select_opening_subject(document, config):
    """Match only the action that begins the first independent opening clause."""
    first_page = document.text.split("\f", 1)[0]
    title = re.search(config["patterns"]["header"], first_page[:2400], FLAGS)
    if title is None:
        return None
    letterhead = first_page[:title.start()]
    if (not OPENING_ADDRESS.match(letterhead) or not OPENING_APPELLANT.search(letterhead)
            or DRAFT.search(letterhead) or BORROWED.search(letterhead)
            or not CLOSED_QUOTES.fullmatch(letterhead)):
        return None

    opening_end = document.starts[2][0] if len(document.starts) > 2 else len(document.text)
    opening = document.text[:opening_end]
    cursor = OPENING_GAP.match(opening, title.end()).end()
    # An explicitly bounded quotation may precede the appellant's first statement.
    quote = QUOTE_OPENING.match(opening, cursor)
    if quote:
        closing = QUOTE_CLOSING.search(opening, quote.end())
        if not closing or not CLOSED_QUOTES.fullmatch(opening[quote.end():closing.start()]):
            return None
        cursor = OPENING_GAP.match(opening, closing.end()).end()
    declaration = OWN_OPENING.match(opening, cursor)
    if declaration is None:
        return None

    offset = declaration.end()
    section = OPENING_END.search(opening, offset)
    stop = section.start() if section else opening_end
    clause = Fragment(opening[offset:stop], offset).before(CLAUSE_END).stripped()
    if not clause.text or document.page(clause.offset) != document.page(declaration.start()):
        return None
    specific = select_filing_subject(document, config, clause, nominative=bool(declaration["subject"]))
    if specific is not None:
        return specific
    framing = DECISION_PREFIX.match(clause.text)
    subject = clause.slice(framing.end()) if framing else clause
    for rule in config["reasons"]["rules"]:
        reason_id = rule["id"]
        match = re.match(rule["pattern"], subject.text, FLAGS)
        if match is None:
            continue
        context = CONTEXTUAL_SUBJECTS.get(reason_id)
        if reason_id == 3 and re.match(r"wyklucz", subject.text, FLAGS):
            context = EXCLUDED_ACTOR
        if context is not None:
            match = context.match(subject.text)
            if match is None:
                return None
        page = document.page(clause.offset)
        end = subject.offset + match.end()
        if document.page(end - 1) != page:
            return None
        description = config["reasons"]["descriptions"][str(reason_id)]
        return FilingSubject(reason_id, description, page, clause.offset, end,
                             "przedmiot_we_własnej_formule_wniesienia")
    return None


def filing_subject_extractor(extract_document, source_clause):
    """Wrap the pinned extractor and fill only its unresolved first-action pair."""
    def extract_with_subject(document, classes):
        value, record = extract_document(document, classes)
        if value is None or record["class"] != "odwolanie":
            return value, record
        decision = record.get("first_allegation") or {}
        # The W0 filing rule was itself applied only after the original A3
        # selected its generic fallback. Preserve every other decided A3 result.
        from_filing_rule = decision.get("rule") == FILING_RULE
        if not decision.get("fallback") and not from_filing_rule:
            return value, record
        config = classes["odwolanie"]
        declaration = source_clause(document, config)
        witness = select_filing_subject(document, config, declaration)
        if witness is None and decision.get("fallback") and declaration is None:
            witness = select_opening_subject(document, config)
        if witness is None:
            return value, record

        action = value["OdwolanieKIO"]
        if from_filing_rule and action["czynnosc_powod_id"] == witness.reason_id:
            return value, record
        action.update(czynnosc_powod_id=witness.reason_id, czynnosc_opis=witness.description)
        start = document.starts[witness.page - 1][0]
        record["first_allegation"] = {
            "page": witness.page, "rule": witness.rule, "fallback": False,
            "source_excerpt": document.text[witness.offset:witness.end],
            "source_span": {"start": witness.offset - start, "end": witness.end - start},
        }
        for key, rule in (("czynnosc_powod_id", witness.rule), ("czynnosc_opis", "opis_kanoniczny_id")):
            record["fields"][f"OdwolanieKIO.{key}"] = {"page": witness.page, "rule": rule}
        return value, record

    return extract_with_subject
