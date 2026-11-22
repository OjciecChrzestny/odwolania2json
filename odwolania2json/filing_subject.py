"""Recover an explicit SWZ or draft-contract subject when the appeal has no selected action."""
from dataclasses import dataclass
import re

from .legal import Fragment
from .model import FLAGS


SPACE = r"[ \t\n]+"
FULL_SPECIFICATION = rf"specyfikacji{SPACE}warunków{SPACE}zamówienia"
SUBJECTS = (
    (4, rf"treści{SPACE}{FULL_SPECIFICATION}(?:[ \t]*\(SWZ\))?"
        rf"{SPACE}(?:opublikowanej|ogłoszonej|udostępnionej)\b"),
    (5, rf"(?:modyfikacji|zmiany){SPACE}(?:treści{SPACE})?(?:SWZ\b|{FULL_SPECIFICATION}\b)"),
    (12, rf"(?:projektowanych{SPACE}postanowień|projektowanego{SPACE}postanowienia){SPACE}umowy\b"),
)
TITLE_LIST = re.compile(
    r"\A[ \t\n]*od[ \t]+czynności(?:[ \t]+i[ \t]+zaniechań)?[ \t]+zamawiającego[ \t.:]*\n"
    r"[ \t\n]*wobec[ \t]*:[ \t.]*\n[ \t\n]*(?:1[.)]|I[.)])[ \t]+",
    FLAGS,
)
BORROWED = re.compile(
    r"^[ \t]*(?:cytat|przytoczenie|treść[ \t]+przytoczonego|pouczenie|uzasadnienie|żądania|wnioski końcowe)\b",
    FLAGS,
)
CLOSED_QUOTES = re.compile(r"""(?:[^„“«"\f]|„[^”\f]*”|“[^”\f]*”|«[^»\f]*»|"[^"\f]*")*""")


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


def select_filing_subject(document, config, declaration=None):
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


def filing_subject_extractor(extract_document, source_clause):
    """Wrap the pinned extractor and fill only its unresolved first-action pair."""
    def extract_with_subject(document, classes):
        value, record = extract_document(document, classes)
        if value is None or record["class"] != "odwolanie" or not record.get("first_allegation", {}).get("fallback"):
            return value, record
        config = classes["odwolanie"]
        witness = select_filing_subject(document, config, source_clause(document, config))
        if witness is None:
            return value, record

        action = value["OdwolanieKIO"]
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
