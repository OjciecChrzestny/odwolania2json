"""First-reason selector for the appellant's own filing declaration."""

from dataclasses import dataclass
from hashlib import sha256
import re

from .appeal_reason import (
    MASK, MAX_CHARS, MIN_TERMS, SUBJECT, SharedFragment, apply_prediction,
    lexical_scores, nearest, projection, safe_projection,
)
from .extract import extract
from .legal import Fragment, classify_reason
from .model import FLAGS


FILING_RULE = "pierwsza_zaskarżona_czynność_we_wniesieniu"
DECLARATION = re.compile(
    r"\bwnosz(?:ę|imy)[ \t\n]+(?:(?:niniejsze|niniejszym)[ \t\n]+)?odwołanie"
    r"[ \t\n]+(?:od|wobec|na)\b", FLAGS,
)
FILING_ZONE_END = r"^[ \t]*(?:[IVX]+[.)][ \t]+)?(?:uzasadnienie|wnioski końcowe)\b"
FOREIGN_START = (
    r"^[ \t]*(?:cytat|przytoczenie|treść\s+cytatu|"
    r"(?:przytoczenie|treść\s+(?:cytowanego|przytoczonego))\s+"
    r"(?:odwołania|pisma|wypowiedzi|oświadczenia)"
    r"(?:\s+(?:innego\s+wykonawcy|zamawiającego|przystępującego|pełnomocnika))?)[ \t\n]*:"
)
FOREIGN_END = (
    r"^[ \t]*(?:koniec\s+(?:cytatu|przytoczenia)|własne\s+stanowisko|stanowisko\s+własne)"
    r"[ \t]*[.:]?[ \t]*$"
)
ATTRIBUTION_BLOCK = re.compile(rf"(?P<foreign>{FOREIGN_START})|(?:{FOREIGN_END})", FLAGS)
SECTION_END = (
    r"^[ \t]*(?:[IVX]+[.)][ \t]+)?"
    r"(?:uzasadnienie|żądania|wnioski końcowe|podstawy prawne|zarzuty)\b"
    r"|\bzarzuc(?:am(?:y)?|a|ają)\b|\bwnosz(?:ę|imy)\s+o\b"
    r"|\b(?:żądam(?:y)?|domagam(?:y)?\s+się)\b|\bwobec\s+powyższego\b"
    rf"|{FOREIGN_START}"
)
QUOTED = re.compile(r'„[^”]*(?:”|$)|«[^»]*(?:»|$)|"[^"]*(?:"|$)')
ATTRIBUTION = re.compile(
    r"^[ \t]*(?:cytat|przytoczenie|treść (?:cytatu|pisma)|(?:inny )?wykonawca|zamawiający)"
    r"(?:[ \t]+(?:napisał|wskazał|oświadczył))?[ \t]*:[ \t]*$", FLAGS,
)
BARE_LIST = re.compile(r"\A\s*:")
LIST_HEADER = re.compile(r"\b(?:następując\w*|czynnoś\w*|zaniechani\w*)\b", FLAGS)
LIST_MARK = re.compile(r"(?:^[ \t]*|(?<=:)[ \t]*)(?P<marker>\(?[0-9]+[.)]|[IVX]+[.)]|[a-d][.)]|[-–—•])[ \t]+", FLAGS)
FIRST_MARK = re.compile(r"(?:\(?1|[ila])[.)]|[-–—•]", re.I)
CLAUSE_END = r";|\.(?=\s+(?-i:[A-ZĄĆĘŁŃÓŚŹŻ]))"
# A legal action and its named object are independently substantive.
ACTION_OBJECTS = frozenset("""
postępowanie postępowaniu postępowania postępowaniem
wykonawca wykonawcy wykonawcę wykonawcą wykonawców wykonawcom
odwołujący odwołującego odwołującemu
""".split())
# A long preamble or uncertain layout cannot deposit an unrelated later excerpt.
SCOPE_LIMIT = 1600


def unattributed(text, mark, quotes, boundaries):
    if any(quote.start() <= mark.start() < quote.end() for quote in quotes):
        return False
    boundary = next((event for event in reversed(boundaries) if event.start() < mark.start()), None)
    if boundary and boundary["foreign"]:
        return False
    previous_lines = text[:mark.start()].splitlines()
    # A quote label on this line or immediately above takes precedence.
    current = previous_lines[-1] if previous_lines else ""
    previous = previous_lines[-2] if len(previous_lines) > 1 else ""
    return not (ATTRIBUTION.fullmatch(current) or (not current.strip() and ATTRIBUTION.fullmatch(previous)))


def source_clause(document, config):
    body = Fragment(document.text).after(config["patterns"]["header"]).before(FILING_ZONE_END)
    quotes = list(QUOTED.finditer(body.text))
    boundaries = list(ATTRIBUTION_BLOCK.finditer(body.text))
    declaration = next((mark for mark in DECLARATION.finditer(body.text)
                        if unattributed(body.text, mark, quotes, boundaries)), None)
    if declaration is None:
        return None
    scope = body.slice(declaration.end(), declaration.end() + SCOPE_LIMIT).before(SECTION_END)
    marker = LIST_MARK.search(scope.text)
    if marker:
        prefix = scope.text[:marker.start()]
        bare = BARE_LIST.match(prefix) and not any(word in SUBJECT for word in projection(prefix).split())
        if bare or (LIST_HEADER.search(prefix) and prefix.rstrip().endswith(":")):
            if not FIRST_MARK.fullmatch(marker["marker"]):
                return None
            scope = scope.slice(marker.end())
            following = LIST_MARK.search(scope.text)
            if following:
                scope = scope.slice(0, following.start())
        else:
            scope = scope.slice(0, marker.start())
    return scope.before(CLAUSE_END).stripped()


@dataclass(frozen=True)
class FilingEvidence:
    fragment: SharedFragment
    quote: Fragment
    required_reason_id: int | None = None
    rule_reason_id: int | None = None


def has_substance(text):
    tokens = text.split()
    return (safe_projection(text) and any(token in SUBJECT for token in tokens)
            and sum(token in SUBJECT or token in ACTION_OBJECTS for token in tokens) >= MIN_TERMS)


def project_by_page(document, source):
    first = document.page(source.offset)
    last = document.page(source.offset + len(source.text) - 1)
    pieces, positions = [], []
    cursor = 0
    for page in range(first, last + 1):
        start = max(source.offset, document.starts[page - 1][0])
        next_page = document.starts[page][0] if page < len(document.starts) else len(document.text)
        end = min(source.offset + len(source.text), next_page)
        raw = Fragment(document.text[start:end], start).stripped()
        text = projection(raw.text)
        if pieces and pieces[-1].split()[-1] == MASK and text.split()[:1] == [MASK]:
            text = text[len(MASK):].lstrip()
        if text:
            positions.append((cursor, cursor + len(text), page, raw))
            pieces.append(text)
            cursor += len(text) + 1
    text = " ".join(pieces)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS + 1].rsplit(" ", 1)[0]
    return text, [position for position in positions if position[0] < len(text)]


def select_filing_evidence(document, config):
    source = source_clause(document, config)
    if source is None or not source.text:
        return None
    source = source.slice(0, MAX_CHARS).stripped()
    text, pages = project_by_page(document, source)
    if not has_substance(text):
        return None
    match = classify_reason(Fragment(text), config)
    required_reason = None
    if len(pages) == 1:
        _, _, page, quote = pages[0]
    else:
        if match is None:
            return None
        reason_id, offset = match
        witness = next((part for part in pages if part[0] <= offset < part[1]), None)
        if witness is None:
            return None
        start, stop, page, quote = witness
        page_text = text[start:stop]
        # The actual matched occurrence must support the same reason within one physical page.
        if not has_substance(page_text) or classify_reason(Fragment(page_text, start), config) != match:
            return None
        required_reason = reason_id
    shared = SharedFragment(
        text=text, page=page, through_page=document.page(source.offset + len(source.text) - 1),
        selector=FILING_RULE, input_sha256=sha256(text.encode("utf-8")).hexdigest(),
    )
    return FilingEvidence(shared, quote, required_reason, match[0] if match else None)


def select_filing(document, config):
    evidence = select_filing_evidence(document, config)
    return evidence.fragment if evidence else None


def filing_extractor(profile="rule", *, ranker=None):
    """Ordinary process(extract_document=...) hook with no corpus or model artifact dependency."""
    if profile not in ("rule", "lexical", "rank") or (profile == "rank" and ranker is None):
        raise ValueError("invalid_filing_profile")

    def one_document(document, classes):
        value, record = extract(document, classes)
        if record["class"] != "odwolanie" or not (record.get("first_allegation") or {}).get("fallback"):
            return value, record
        config = classes["odwolanie"]
        evidence = select_filing_evidence(document, config)
        if evidence is None:
            return value, record
        fragment = evidence.fragment
        descriptions = config["reasons"]["descriptions"]
        if profile == "rule":
            prediction = evidence.rule_reason_id
        elif profile == "lexical":
            prediction = nearest(lexical_scores(fragment.text, descriptions))
        else:
            try:
                prediction = ranker(fragment.text)
            except (OSError, RuntimeError, ValueError):
                prediction = None
        if evidence.required_reason_id is None or prediction == evidence.required_reason_id:
            apply_prediction(value, record, fragment, prediction, descriptions, method=FILING_RULE)
        return value, record

    return one_document
