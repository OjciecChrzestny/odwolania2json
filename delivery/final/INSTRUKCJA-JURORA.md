# Odwołania2JSON dla jurora UZP

## Czysta kopia i własny PDF

Potrzebujesz Git oraz linku i pełnego SHA wskazanych w zgłoszeniu. Poniższe polecenia są dla Linuksa. Do instalacji zależności lub budowy obrazu potrzebna jest sieć. Samo przetwarzanie odbywa się lokalnie.

```sh
: "${REPO_URL:?Ustaw REPO_URL na adres repozytorium ze zgłoszenia}"
: "${RELEASE_SHA:?Ustaw RELEASE_SHA na pełny SHA ze zgłoszenia}"
WORK="$(mktemp -d)"
git clone --no-checkout "$REPO_URL" "$WORK/repo"
cd "$WORK/repo"
git checkout --detach "$RELEASE_SHA"
git rev-parse HEAD

: "${PDF:?Ustaw PDF na bezwzględną ścieżkę do własnego PDF-u}"
IN="$WORK/PDF jurora"
OUT="$WORK/JSON jurora"
DIAG="$WORK/Diagnostyka jurora"
mkdir -p "$IN/sprawa" "$OUT" "$DIAG"
cp "$PDF" "$IN/sprawa/pismo.pdf"
```

Możesz dodać dalsze PDF-y także w innych podkatalogach wejścia. Aby sprawdzić OCR bez własnych danych, ustaw `PDF="$PWD/delivery/compose/skan-syntetyczny.pdf"` po wejściu do repozytorium i przed skopiowaniem PDF-u. Uruchom wtedy wariant z OCR. Skan powinien dać `kwota=123.45`, tytuł „Opłata za usługę” i `ocr_pages=[1]`.

### Python

Utwórz środowisko w repozytorium. Dla nowszej wersji Pythona podstaw jej polecenie zamiast `python3.13`.

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Dla PDF-ów z warstwą tekstową uruchom:

```sh
python -m odwolania2json --input "$IN" --output "$OUT" \
  --diagnostics "$DIAG/last-run.json"
```

Dla skanów wykonaj pierwszy blok poleceń z [instalacji polskiego OCR](../../README.md#opcjonalny-ocr). Po potwierdzeniu sumy użyj tego samego katalogu `TESSDATA`. Uruchom:

```sh
OMP_THREAD_LIMIT=1 python -m odwolania2json --input "$IN" --output "$OUT" \
  --diagnostics "$DIAG/last-run.json" --ocr-data "$TESSDATA"
```

### Docker Compose z OCR

Uruchom na silniku Docker obsługującym kontenery linuksowe, z Compose v2 i BuildKit. W trybie rootless wykonaj `export ODW_UID=0 ODW_GID=0` po ustawieniu identyfikatorów z przykładu, przed uruchomieniem kontenera.

```sh
OUT="$WORK/JSON Compose"
DIAG="$WORK/Diagnostyka Compose"
export ODW_INPUT_DIR="$IN" ODW_OUTPUT_PARENT="$WORK" ODW_OUTPUT_NAME="$(basename "$OUT")"
export ODW_DIAGNOSTICS_DIR="$DIAG"
export ODW_UID="$(id -u)" ODW_GID="$(id -g)"
mkdir -p "$OUT" "$DIAG" "$WORK/.${ODW_OUTPUT_NAME}.odwolania2json"
docker compose build cli
docker compose run --rm --pull never -e OMP_THREAD_LIMIT=1 cli
```

Kontener ma wyłączoną sieć i montuje katalog wejściowy tylko do odczytu. [Domyślne katalogi Compose, konfiguracja Windows i ewidencja wyników](../compose/README.md)

### Wynik i źródło pola

Przy poprawnym odczycie `sprawa/pismo.pdf` ma odpowiadający plik `sprawa/pismo.json`. Diagnostyka jest obok wyjścia.

```sh
wc -c "$OUT/sprawa/pismo.json"
cat "$OUT/sprawa/pismo.json"
cat "$DIAG/last-run.json"
```

Plik 0 B i status `negative` oznaczają dokument obcy. Przy błędzie odczytu danego PDF-u wynik jest pomijany, wpis ma status `read_error`, a CLI kończy pozostałe PDF-y i zwraca kod 1. Kod 2 oznacza błąd konfiguracji lub operacji na drzewie. Puste wejście daje zero wyników i pustą listę `documents`. Przy nowym przebiegu możesz wskazać nowe wyjście i nową diagnostykę.

Dla rozpoznanego przelewu odszukaj np. `przelew_bankowy.kwota`. W `documents` wybierz rekord z `output: sprawa/pismo.json`, a w jego `fields` odczytaj `page` i `rule`. `page` liczymy od 1. Otwórz stronę PDF-u i porównaj wartość. W natywnym środowisku Pythona skrypt może wypisać warstwę tekstową wskazanej strony. Dla strony rozpoznanej przez OCR obejrzyj obraz w czytniku PDF.

```sh
python demo/rozszerzalnosc/pokaz.py zrodlo "$IN/sprawa/pismo.pdf" \
  "$DIAG/last-run.json" --output sprawa/pismo.json
```

## Skąd bierze się wynik

1. `extract.py` odczytuje przez pypdf maksymalnie sześć pierwszych stron. Jeśli włączono OCR, `ocr.py` renderuje wybrane strony przez PDFium i rozpoznaje polski tekst przez Tesseract.
2. `model.py` wczytuje definicje klas. `odwolanie.json` odpowiada odwołaniom KIO, `pelnomocnictwo.json` pełnomocnictwom, a `przelew.json` potwierdzeniom przelewu. Punktowane sygnały z treści i progi wyłaniają jedną klasę. Brak rozpoznania lub remis daje dokument obcy. Nazwy PDF-ów służą do wyznaczenia ścieżki wynikowej.
3. Reguły pól i operacje w `operations.py` normalizują wartości, a schemat określa klucze, typy i pola dopuszczające `null`. Logika dokumentów prawnych jest w `legal.py`. Dane przelewów korzystają też z `transfer.py` i reguł dla skanów i rachunków.
4. `python -m odwolania2json` zapisuje wyniki zgodnie z drzewem wejścia. Osobny plik diagnostyczny wskazuje status, klasę oraz podstawę wydobycia pola na poziomie strony i reguły.

Aby zmienić konfigurację ekstrakcji lub dodać klasę, skopiuj standardowe konfiguracje do osobnego katalogu wskazanego przez `--config KATALOG`. Każda definicja ma unikatową nazwę, sygnały, próg i schemat. Dla klasy `zawiadomienie` wystarcza jeden dodatkowy plik JSON z regułami pól `sygnatura` i `termin`. Próba podaje dokładne polecenia, dwa przykłady oraz podobne pismo obce. [Konfiguracja klas](../../README.md#reguły-i-rozszerzanie) · [Próba rozszerzenia](../../demo/rozszerzalnosc/README.md)

## Zgłoszenie, finał i przekazanie

| Etap | Materiały i warunki |
| --- | --- |
| Zgłoszenie w HackTribe | Tytuł „Odwołania2JSON” i link GitHub do działającego prototypu. Instrukcja HackTribe przewiduje prezentację w PDF do 10 MB przy końcowym zgłoszeniu. Dokumentacja techniczna i własne wyniki są materiałami dodatkowymi według README UZP. |
| Preselekcja UZP | F1 na nieujawnionym zbiorze co najmniej 10 spraw. |
| Finał UZP | Maksymalnie trzy zespoły. F1 stanowi 50%, elastyczność i łatwość dodawania klas stanowią 50%. Dowody to kod, opis architektury i prezentacja. W prezentacji wskaż komponenty zewnętrzne. |
| Przekazanie przez zwycięzcę | Kod źródłowy, instrukcja startu, konfiguracja Docker Compose i dokumentacja architektury, konfiguracji ekstrakcji danej klasy i dodawania klasy. § 3 i § 4 regulaminu określają też warunki umowy przeniesienia praw. |

Według instrukcji HackTribe projekt i wybór zadania należało zapisać do 20:00 w sobotę 21 listopada. Termin końcowy to 11:00 w niedzielę 22 listopada 2026 r., czasu warszawskiego. Szczegółowy opis PDF podaje podział finału 50/30/20. Do finału UZP stosujemy § 2 regulaminu zadania. [README UZP, rewizja z 21 listopada](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/0b360a9da4b482a6a280696df6714404e0953505/README.md#4-wymagania-formalne) · [Regulamin UZP, § 2–4](https://mudnibfuppwadjkynscc.supabase.co/storage/v1/object/public/task-files/057d36b5-cb92-4062-9393-983cb8a96088/files/aa36e74b-f96c-46cf-9970-5937ed203222.pdf#page=2) · [Szczegółowy opis UZP](https://mudnibfuppwadjkynscc.supabase.co/storage/v1/object/public/task-files/057d36b5-cb92-4062-9393-983cb8a96088/files/aeabc57d-7420-4069-946e-2c4de71d87ed.pdf#page=4) · [Przewodnik HackNation](https://hacknation.pl/przewodnik-uczestnika) · [Instrukcja HackTribe, s. 6–7](https://hacknation.pl/api/public/przewodnik/1f73a661-0852-4e9e-b3ed-58c93bce6456?asset=aa346c52-8bd9-44ac-9499-364e44c4b6b4#page=6)

**Dostęp z konta jurora pozostaje niezweryfikowany.** Właściciel potwierdza adres i SHA zgłoszenia, odczyt prywatnego repozytorium z właściwego konta oraz możliwość pobrania przesłanej prezentacji. Zaproszenia i wysyłka zgłoszenia należą do właściciela.

## Warunki użycia API

A3 uruchamiane z tego przewodnika przetwarza dokumenty lokalnie. `experiments/abc` i `experiments/transfer_api` zawierają oddzielne eksperymenty. Działanie A3 i dostęp do niego nie wymagają klucza API.

W README UZP sprawdzonym 21 listopada 2026 r. wymagane są komponenty open source, w tym otwartoźródłowe modele językowe. Wariant korzystający z LLM ma używać API i być dostarczony z kluczem testowym. Dostawca ma świadczyć usługę z serwerów w UE/EOG i określać zakres oraz miejsce przetwarzania w polityce prywatności. OCR przez API podlega ocenie parametrów jak LLM. Organizator zapowiedział aktualizację szczegółowych zasad punktacji modeli. W razie wyboru wariantu z API właściciel potwierdza zgodność modelu, dostawcy i regionu, limity oraz kanał przekazania klucza poza Git. Limit testu organizatora to 45 minut na 150 PDF-ów. [Wymagania techniczne i walidacja UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/0b360a9da4b482a6a280696df6714404e0953505/README.md#5-wymagania-techniczne) · [Dokumentacja eksperymentu B/C](../../experiments/abc/README.md#dostawcy-i-warunki-sprawdzone-21112026)

## Komponenty zewnętrzne

| Zakres | Komponent i źródło licencji |
| --- | --- |
| Uruchomienie | Python 3.13+, [PSF License](https://docs.python.org/3.13/license.html). |
| Odczyt PDF | pypdf 6.21.4, [BSD-3-Clause](https://pypi.org/project/pypdf/6.21.4/). |
| OCR | pypdfium2 5.15.2 i PDFium, [licencje pakietu i PDFium](https://github.com/pypdfium2-team/pypdfium2/blob/5.15.2/README.md#licensing). tesserocr 2.13.0, [MIT](https://github.com/sirfz/tesserocr/blob/master/LICENSE), Tesseract i polskie dane `tessdata_fast` 4.1.0, [Apache-2.0 dla silnika](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE) i [danych](https://github.com/tesseract-ocr/tessdata_fast/blob/4.1.0/LICENSE). |
| Kontener | [Oficjalny obraz Python](https://hub.docker.com/_/python) przypięty przez digest w `Dockerfile`. [Licencja silnika Moby](https://github.com/moby/moby/blob/master/LICENSE) i [licencja Compose](https://github.com/docker/compose/blob/main/LICENSE). |
| Budowa pokazu | [ReportLab](https://pypi.org/project/reportlab/4.4.10/), [Pillow](https://pypi.org/project/pillow/13.0.0/), [charset-normalizer](https://pypi.org/project/charset-normalizer/3.5.2/), [Lato](https://github.com/latofonts/lato-source) i [DejaVu Sans Mono](https://dejavu-fonts.github.io/License.html). Wersje bibliotek w `requirements-pokaz.txt`. |
| Dane porównawcze | Publiczne przykłady i schematy organizatora w [przypiętej rewizji UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/de135d20811caf630f3e94dc655ba5eebd9a6710). Skan próbny w repozytorium jest syntetyczny. |

## Dowody do finału

- Czysty start na własnym wejściu, plik wynikowy i przejście do wskazanej strony źródłowej według instrukcji powyżej.
- Dodanie klasy z jednym plikiem JSON, dwa rozpoznane przykłady oraz pismo obce dające 0 B. [Próba rozszerzenia](../../demo/rozszerzalnosc/README.md)
- [Prezentacja](prezentacja.pdf) · [Scenariusz](SCENARIUSZ.md) · [Ekrany rezerwowe](ekrany-rezerwowe.pdf)

Metryki zgłoszenia wymagają potwierdzenia na jednym kandydacie wydania. Dotychczasowe raporty opisują własne próby na wskazanych w nich rewizjach i zbiorach. [Rozwój A3](../../RAPORT_A3.md) · [Historyczna próba A3 na skanach](../../RAPORT_KONCOWY_A3.md) · [Historyczna zgodność Compose](../compose/RAPORT.md)
