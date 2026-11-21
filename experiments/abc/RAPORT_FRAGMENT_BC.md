# Pierwszy zarzut bez dopasowania reguły A

Baza `8a2219ed0707308b6034721381bd3073aec00e90`. Kod i testy `7a788965dc9f27eb24c31720d07d79e6e160f788`. Zmiana selektora jest w [selector-a.patch](selector-a.patch), który odbiór stosuje w tymczasowym klonie.

## Wynik przed i po

Na dwustronicowym syntetycznym PDF-ie pierwszy zarzut brzmi „Zamawiający pozbawił wykonawcę prawa dalszego udziału w postępowaniu.”. Drugi dotyczy wyboru najkorzystniejszej oferty. W obu próbach selektor wykrył `pierwszy_numerowany_zarzut` na stronie 2. Domyślny A w obu próbach zapisał awaryjne ID 11 i datę `null`.

| Wersja | Wariant | Próby na PDF | ID wyjścia | Powrót do A |
| --- | --- | ---: | ---: | --- |
| Przed | B | 0 | 11 | `no_reliable_fragment` |
| Przed | C | 0 | 11 | `no_reliable_fragment` |
| Po | B, odpowiedź atrapy 3 | 1 | 3 | — |
| Po | C, odpowiedź atrapy 8 | 1 | 8 | — |

Regresja przed poprawką zakończyła się oczekiwaną porażką dla B i C przy sprawdzeniu liczby prób. Po poprawce obie atrapy dostały wyłącznie dokładny pierwszy fragment wraz z końcowym LF. Treść wspólnego żądania po usunięciu identyfikatora modelu była identyczna. Test porównał pełny wynik z A po uwzględnieniu dwóch dozwolonych zmian. Opis odpowiadał ID ze słownika A, a data pozostała taka jak w A.

- SHA-256 fragmentu `1b74959c3d159c4d31d8f0514637b6b92c4b488491d0ef31f0dc9a9e214145a8`
- SHA-256 wspólnego żądania `1f6b3d1d281950a70c70677c4cc15be0f7fd04b1a27e8720d207f6a03adb5eeb`
- SHA-256 pliku wyniku A dla tej próby `49db25e2bd7019db6e970e1265b02afef5fe933a45c163efa2f32e9683355116`

Po symulowanym HTTP 429 dla B i przekroczeniu limitu czasu dla C każdy wariant wykonał jedną próbę dla pierwszego PDF-u. Zachował jego wynik A bajt w bajt, zapisał odpowiednio `http_429` i `timeout` i przetworzył drugi PDF z ID 11 dopasowanym przez regułę A. Pusty fragment po rozpoznanym nagłówku i brak zarzutu dały zero prób i `no_reliable_fragment`. Bez klucza nowo kwalifikujący się PDF dał zero prób i `missing_key`. Przelew, pełnomocnictwo i dokument obcy również dały zero prób.

## Diagnostyka i zakres

- `allegation_structure` zapisuje regułę i stronę wskazaną przez selektor struktury, albo `null` przy braku struktury.
- `first_allegation` zawiera ID, regułę i flagę decyzji awaryjnej A. Dopasowane przez A ID 11 ma `fallback=false`.
- `decision_source` wskazuje regułę, offset, strony i SHA-256 dokładnego fragmentu. Zachowuje dotychczasowe przycięcie i wybór wcześniejszego opisu tam, gdzie A na nim polega.
- `experiment` zapisuje próbę transportu, wynik i kod przyczyny ewentualnego powrotu do A.

Nowa wersja rozszerza zbiór PDF-ów kwalifikujących się do B/C o rozpoznane, niepuste pierwsze fragmenty bez dopasowania ID przez A. Porównanie raportów B i C kontroluje zgodność struktury oraz źródła fragmentu. Porównywane przebiegi należy przygotować z tej samej rewizji eksperymentu.

## Odbiór

Na VPS, Python 3.13.18 i pypdf 6.21.4:

```sh
LANDLOCK=1 PYTHON=python sh experiments/abc/test-offline.sh
```

TCP było zablokowane przez Landlock. Przeszło 8 testów eksperymentu oraz 7 regresji A, w tym dotychczasowa próba 32 PDF-ów z 10 parami identycznych żądań. W dodatkowym sprawdzeniu `python -m odwolania2json` zapisało identyczne bajtowo 6/6 wyników i plik diagnostyczny bez patcha oraz ze starą i nową wersją patcha.

Wyniki dotyczą kontroli technicznej na syntetykach. Nie użyto kluczy, nie wywołano API i nie otwierano walidacji ani odłożonych spraw. Jakość, opóźnienie i koszt dostawców, a także skala rozszerzenia kwalifikacji na rzeczywistych dokumentach pozostają niezmierzone. Następny krok koordynatora to przegląd patcha przed rozważeniem osobnego pomiaru.
