"""Projection and scoring of a bounded excerpt from a filed appeal."""

from collections import Counter
from dataclasses import dataclass
from math import isfinite, sqrt
import re
import unicodedata


MARGIN = 0.02
MAX_CHARS = 720
MIN_TERMS = 2
MASK = "[pominięto]"
TOKEN = re.compile(r"[^\W\d_]+|[.,:;!?()]|\s+|[^\s]")
WORD = re.compile(r"[^\W\d_]+")
PUNCTUATION = frozenset(".,:;!?()")
# A closed vocabulary releases whole forms only. No wildcards accept names or identifiers.
SUBJECT = frozenset("""
odrzucenie odrzucenia odrzuceniu odrzuceniem odrzucić odrzucił odrzuciła odrzucono
odrzucona odrzuconej odrzuconą odrzucając odrzucać odrzuca
wykluczenie wykluczenia wykluczeniu wykluczeniem wykluczyć wykluczył wykluczono wykluczony
wykluczona wykluczając wykluczającego wykluczającej
wybór wyboru wyborze wyborem wybrał wybrała wybrano wybiera wybierając wybierze
oferta oferty ofert ofertę ofercie ofertą ofertami
zaniechanie zaniechania zaniechaniu zaniechaniem zaniechał zaniechano zaniechawszy
pominięcie pominięcia odstąpienie odstąpienia odstąpił odstąpiono
unieważnienie unieważnienia unieważnieniu unieważnieniem unieważnił unieważniono unieważnić
specyfikacja specyfikacji specyfikację specyfikacją treść treści treścią swz opz siwz
modyfikacja modyfikacji modyfikację modyfikacją zmodyfikował zmodyfikowanie zmodyfikowania
zmienił zmieniono zmiana zmiany zmian zmianę zmianie
odpowiedź odpowiedzi odpowiedział wyjaśnienie wyjaśnienia wyjaśnień wyjaśnieniu wyjaśnił wyjaśniono
publikacja publikacji publikację opublikował opublikowano opublikowanie ogłoszenie ogłoszeniu ogłosił
udostępnienie udostępnienia udostępnił udostępniono ustaleniu ustalenie ustalenia sformułowanie
opis opisu opisie opisaniu opisanie opisał opisano opisem przedmiot przedmiotu przedmiotem
projektowane projektowanych projektowanym projektowanego projektowany projektowana projekt
postanowienia postanowień postanowienie postanowieniach wzór wzoru wzorze umowa umowy umowę umowie
pozbawienie pozbawieniu pozbawił pozbawiła dopuszczenie dopuszczenia dopuszczeniu
dopuszczono niedopuszczenie niedopuszczenia odmowa odmowie odmowy odmówił
""".split())
PUBLIC_WORDS = SUBJECT | frozenset("""
a albo ani ale aby bez bo by celem co czy dla do gdy gdyż i ich iż jak jako
jeżeli że je jej jego jest jeśli które którego której którym których lecz lub ma mają
mimo na nad nie nim niż o od oraz po pod poprzez poza przed przez przy się są tak także
te ten tego temu tej tym to tylko w we wobec wskutek wbrew wraz wynik wyniku z za ze żeby
art ust pkt lit pzp dokumentacja dokumentacji wymagania wymaganie wymagań
warunek warunki warunku warunków zamówienie zamówienia zamówień zamówieniu
zamawiający zamawiającego zamawiającemu wykonawca wykonawcy wykonawcę wykonawcą wykonawców wykonawcom
odwołanie odwołania odwołaniu odwołujący odwołującego odwołującemu konkurencja
kryteria kryterium ocena oceny ocenę ocenie badanie badania badaniu czynność czynności czynnością
decyzja decyzji decyzję ogłoszenia zarzut zarzutu zarzuty zarzutów zarzucam zarzucamy zarzuca
naruszenie naruszenia naruszeniu naruszył uzasadnienie uzasadnienia ustawa ustawą ustawy przepisy
przepis przepisu przepisów prawem prawa prawu niezgodność brak braku
niespełnienie niespełnienia niespełniła spełnienia spełnia spełniła udział udziału udziałem
możliwość możliwości dalszego uprawnienie uprawnienia terminu termin wymagane wymaganych
niezgodnej niezgodnego niezgodnych niezgodny niezgodne bezprawny bezprawnie
dokonanie dokonania dokonaniu dokonał dokonano najkorzystniejsza najkorzystniejszej najkorzystniejszą
najkorzystniejsze najkorzystniejszych innych wnoszę wnosimy wnosi informacja informacji
przekazanie przekazania przekazał przekazano dotyczące dotyczących ponowną ponowne ponownego
postępowanie postępowania postępowaniu postępowaniem postępowań
""".split())


@dataclass(frozen=True)
class SharedFragment:
    text: str
    page: int
    through_page: int
    selector: str
    input_sha256: str


def projection(text):
    words = []
    for match in TOKEN.finditer(unicodedata.normalize("NFC", text).casefold()):
        token = match.group()
        if token.isspace():
            continue
        if token in PUBLIC_WORDS or token in PUNCTUATION:
            words.append(token)
        elif not words or words[-1] != MASK:
            words.append(MASK)
    return " ".join(words)


def safe_projection(text):
    return (isinstance(text, str) and bool(text) and len(text) <= MAX_CHARS
            and all(word in PUBLIC_WORDS or word in PUNCTUATION or word == MASK for word in text.split()))


def ngrams(text):
    counts = Counter()
    for word in WORD.findall(text.casefold().replace(MASK, " ")):
        padded = "^" + word + "$"
        for size in (3, 4, 5):
            counts.update(padded[index:index + size] for index in range(len(padded) - size + 1))
    return counts


def lexical_scores(text, descriptions):
    query = ngrams(text)
    if not query:
        return {}
    norm = sqrt(sum(value * value for value in query.values()))
    scores = {}
    for reason, description in descriptions.items():
        label = ngrams(description)
        label_norm = sqrt(sum(value * value for value in label.values()))
        scores[int(reason)] = sum(query[token] * value for token, value in label.items()) / (norm * label_norm)
    return scores


def nearest(scores):
    if set(scores) != set(range(1, 13)) or any(not isfinite(score) for score in scores.values()):
        return None
    best, second = sorted(scores, key=lambda reason: (-scores[reason], reason))[:2]
    return best if scores[best] > 0 and scores[best] - scores[second] >= MARGIN else None


def apply_prediction(value, record, fragment, prediction, descriptions, *, method):
    """Apply a guarded suggestion from the normal process extract_document callback."""
    if (value is None or record["class"] != "odwolanie" or not record["first_allegation"]["fallback"]
            or fragment is None or type(prediction) is not int or str(prediction) not in descriptions):
        return False
    action = value["OdwolanieKIO"]
    action["czynnosc_powod_id"] = prediction
    action["czynnosc_opis"] = descriptions[str(prediction)]
    record["first_allegation"] = {"page": fragment.page, "rule": method, "fallback": False}
    for key, rule in (("czynnosc_powod_id", method), ("czynnosc_opis", "opis_kanoniczny_id")):
        record["fields"][f"OdwolanieKIO.{key}"] = {"page": fragment.page, "rule": rule}
    return True
