# Archiwalne próby prezentacji na VPS

## Archiwalne PDF-y

Poniższe pliki dokumentują wcześniejszą rewizję A3 `5fa11680eac824896839ef4b7f281e1f54b3ed68`. Parametry OCR, metryki i konfiguracja na stronach odnoszą się do tamtej próby.

- [Archiwalna prezentacja A3](archiwum/prezentacja-a3-5fa11680eac8.pdf)
- [Archiwalne ekrany rezerwowe A3](archiwum/ekrany-rezerwowe-a3-5fa11680eac8.pdf)

[Polecenia do wygenerowania aktualnych materiałów](SCENARIUSZ.md#uruchomienie-na-vps).

## Próba A3 po połączeniu prac

Z czystego klonu rewizji `5fa11680eac824896839ef4b7f281e1f54b3ed68` na VPS uruchomiono publiczne CLI w kontenerze Docker z wyłączoną siecią. PDF-y pokazu i ekranów rezerwowych pochodzą z tego przebiegu.

| Próba | Wynik |
| --- | --- |
| Własny katalog z syntetycznymi PDF-ami | Sześć pól przelewu, w tym kwota 123,45 zł ze strony 1. Wezwanie do zapłaty dało plik 0 B. |
| Rozszerzenie jednym plikiem konfiguracji | Dwa zawiadomienia z poprawnymi sygnaturami i terminami. Pierwszy termin pochodzi ze strony 2. Pismo obce dało 0 B. Cztery pierwotne wyniki zachowały identyczne SHA-256. |
| Czas na rozgrzanym obrazie | Przygotowanie dokumentów 0,216 s, przelew z weryfikacją 1,283 s, dodanie klasy z regresją 2,464 s. Łącznie 3,963 s dla tych trzech etapów. Próba z głosem prezentera i projektorem czeka na pomiar. |
| Materiały | `prezentacja.pdf` ma 5 stron, a `ekrany-rezerwowe.pdf` ma 3 strony. Odczytano tekst i sprawdzono render wszystkich ośmiu stron. |

Na slajdzie jakości 0,9963 dotyczy A3 na 128 rozwojowych PDF-ach. Wynik 0,9822 pochodzi z wcześniejszego testu końcowego A2 na 31 PDF-ach. A2 pominął pełnomocnictwo, więc miernik oznaczył ten przebieg jako nieważny. Dziesięć spraw odłożonych dla A3 czeka na odrębny test. [Odbiór A3](../../docs/historia/RAPORT_A3.md)

Wyniki próby i czasy są na VPS w `~/uzp-parallel/main-proof/5fa11680eac8/judge/`. [Instrukcja powtórzenia z czystej kopii](SCENARIUSZ.md#uruchomienie-na-vps)

## Archiwalna próba A2

**RC_SHA** `1937848079584ec72aa1307f1305637e93607e1c`
**Raport integratora** `747800f5a536967614686fb6f6210de48e6ce7c3:RAPORT_RC1.md`

Wartość RC_SHA pochodzi z pierwszej linii raportu integratora w klonie `~/uzp-parallel/rc1`. Pokaz uruchomiono jako `dev-viralpay` z osobnego, czystego klonu na wskazanym commicie. Każda próba używała świeżych syntetyków i nowego wyjścia. Docker rootless uruchomił publiczne CLI z `--network none --pull never`, a osobna kontrola wykazała tylko interfejs `lo`. Budowę obrazu i instalację narzędzi wykonano przed pomiarem.

| Próba | Obserwacja |
| --- | --- |
| Potwierdzenie przelewu | Sześć pól zgodnych z oczekiwaniami. Kwota `123.45`, strona 1, reguła `kwota_operacji`. Wezwanie do zapłaty zwróciło 0 B. |
| Dodanie klasy | Diff obu historycznych SHA pokazał jeden plik `demo/rozszerzalnosc/zawiadomienie.json`. Dwa zawiadomienia dały `KIO-DEMO/17/26` i `2026-12-03` oraz `KIO-DEMO/42/27` i `2027-01-18`. Pierwszy termin pochodzi ze strony 2 i reguły `wiersz_terminu`. Dokument obcy zwrócił 0 B. |
| Regresja na RC | 4/4 identycznych SHA-256 przed i po rozszerzeniu na syntetykach. Po jednym odwołaniu, pełnomocnictwie i przelewie oraz jeden negatyw. |
| Regresja rozwojowa z raportu integratora | 11/11 zgodnych ścieżek i SHA-256 oraz 8/8 pustych negatywów. W tej próbie prezentacji użyto wyłącznie syntetyków. |
| Gotowe PDF-y | `prezentacja.pdf` ma 5 stron i **133 567 B**, poniżej 10 MB. `ekrany-rezerwowe.pdf` ma 3 strony i **182 343 B**. Sprawdzono każdą stronę renderem PDFium oraz tekstem wyodrębnionym przez pypdf. Polskie znaki, kwota, data i reguły są czytelne. |

## Czas komend i narracji

| Pomiar na rozgrzanym obrazie | Czas |
| --- | ---: |
| Cały odbiór poleceniem `calosc`, czas ścienny | 4,46 s |
| Przygotowanie syntetyków | 0,268 s |
| Pierwsze wywołanie CLI z kontenerem | 1,102 s |
| Etap przelewu z weryfikacją wyniku i źródła | 1,339 s |
| CLI po dodaniu zawiadomienia | 1,088 s |
| CLI do regresji po dodaniu klasy | 1,131 s |
| Etap dodania klasy z regresją i źródłem | 2,505 s |

Narrację **oszacowano na około 115 s**. Trzy segmenty zawierają 55, 54 i 70 słów. Przy 130 słowach na minutę sama wypowiedź trwa około 83 s. Do przełączania okien i wskazywania pól przyjęto odpowiednio 12, 4 i 13 s. Do tego doliczono zmierzone etapy widocznych komend, łącznie 3,8 s. Otrzymujemy około 39, 29 i 48 s przy limitach 40, 30 i 50 s. Przejście z człowiekiem i projektorem pozostaje do zmierzenia. Trzeba zwłaszcza sprawdzić przejście terminal → druga strona PDF-u w ostatnich 50 sekundach i otwarcie zapisu rezerwowego bez SSH.

## Powtórzenie

Na VPS osobna gałąź prezentacji zawiera źródło `delivery/final/buduj.py`, instrukcję i gotowe PDF-y. Poniższe komendy zakładają zainstalowane narzędzia z `requirements-pokaz.txt`, włączony Docker rootless i fonty Lato oraz DejaVu. Pobieranie i instalacja kończą się przed próbą offline.

```sh
export PATH="$HOME/.local/bin:$PATH" DOCKER_CONTEXT=rootless
DOCS="$HOME/uzp-parallel/prezentacja/delivery/final"
RUNTIME="$HOME/uzp-parallel/prezentacja-runtime"
RC_SHA=1937848079584ec72aa1307f1305637e93607e1c
IMAGE=uzp-prezentacja-1937848:local
RUN="$(mktemp -d "$RUNTIME/powtorka-XXXXXX")"
git clone --no-local --no-checkout "$HOME/uzp-parallel/rc1" "$RUN/kod"
git -C "$RUN/kod" switch --detach "$RC_SHA"
git -C "$RUN/kod" status --short --branch
git -C "$RUN/kod" rev-parse HEAD

# Wykonaj tylko przed próbą offline, jeśli obraz nie jest zbudowany.
docker build --label "org.opencontainers.image.revision=$RC_SHA" \
  --tag "$IMAGE" "$RUN/kod"

# Odbiór offline na zbudowanym wcześniej obrazie.
time "$RUNTIME/venv/bin/python" "$DOCS/proba.py" "$RUN/kod" "$RUN/proba" \
  calosc --sha "$RC_SHA" --image "$IMAGE"
"$RUNTIME/venv/bin/python" "$DOCS/buduj.py" "$RUN/proba" "$RUN/materialy"
```

Dowody z wykonanego przebiegu są w `~/uzp-parallel/prezentacja-runtime/rc-XZxDFh/`. Log pokazowy to `pokaz.log`, pomiary są w `proba/czasy-calosc.json`, a podglądy stron w `qa/`. Po instalacji użyto obrazu `sha256:2b8a3079f551688088e15bc1089c9a4cd902a874ee9bd9c09f6ed13aec4e7519`.

Wynik jury, próba przy projektorze oraz dostęp z konta jurora do prywatnego prototypu pozostają do potwierdzenia. Materiały opisują osobno pomiar A, development A2 oraz próbę syntetyczną.
