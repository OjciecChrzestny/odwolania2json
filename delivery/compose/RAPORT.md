# Odbiór Docker Compose na VPS

Pełny odbiór z 21 listopada 2026 r. przeszedł na Docker Engine w trybie rootless. Na tej samej czystej rewizji natywne CLI i Compose zwróciły identyczne ścieżki i bajty wszystkich sześciu wyników oraz identyczną diagnostykę.

| Identyfikator | Wartość |
| --- | --- |
| Gałąź | `codex/uzp-compose` |
| SHA sprawdzone natywnie i w Compose | `1f6da6c2dcb5789964d49cfcb844f364c40afb07` |
| SHA mierzonego A | `19f702fc58e685f85f2fae14557d14f2c5453cfd` |
| Rewizja danych rozwojowych | `de135d20811caf630f3e94dc655ba5eebd9a6710` |
| Host `hacknation` | Ubuntu 24.04 LTS, Linux 6.8.0-31-generic, x86-64, 6 vCPU, 23,46 GiB RAM |
| Silnik i narzędzia Docker | Engine i klient 29.1.3, kontekst `rootless`, Compose 2.40.3, Buildx 0.30.1 |
| Natywnie i w obrazie | Python 3.13.18, pypdf 6.21.4, pypdfium2 5.15.2, tesserocr 2.13.0 |
| Obraz bazowy w pomiarze | `python:3.13-slim-bookworm@sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72` |

Pakiet CLI, konfiguracja klas i oba pliki zależności są identyczne z mierzonym A według `git diff --exit-code 19f702fc58e685f85f2fae14557d14f2c5453cfd HEAD -- odwolania2json requirements.txt requirements-ocr.txt`. Próba używa czterech PDF-ów z `case_10`, kopii przelewu o tej samej nazwie w innym podkatalogu i syntetycznego jednostronicowego skanu przelewu bez warstwy tekstowej. Przygotowanie sprawdziło rewizję UZP i hashe wejść z manifestu rozwojowego.

## Wyniki

| Próba | Obserwacja |
| --- | --- |
| Budowa poprawionego obrazu | `docker compose build cli`, 8,850 s z obrazem bazowym w pamięci podręcznej i ponowną instalacją zależności |
| Własny folder ze spacją | Natywnie 0,990 s, przez Compose 1,762 s. W obu przebiegach 6 PDF-ów, 6 wyników i 0 błędów odczytu. Posortowane ścieżki, bajty i diagnostyka identyczne. |
| Domyślne katalogi | `docker compose run --rm cli`, 1,90 s. Sześć wyników i diagnostyka identyczne z przebiegiem natywnym. |
| Trzy klasy i negatyw | Oczekiwane klasy z manifestu. `case_10/doc_02.json` ma dokładnie 0 B. |
| Dwie identyczne nazwy | `case_10/doc_04.json` i `duplikat/doc_04.json` istnieją osobno i mają po 390 B o identycznej zawartości. |
| Polski OCR | SHA-256 `pol.traineddata` zgodny z README. Skan dał `kwota=123.45`, `tytul="Opłata za usługę"` i `ocr_pages=[1]`. |
| Pusty folder | 0 wyników i pusta diagnostyka. Natywnie 0,224 s, przez Compose 1,202 s. |
| Ponowne uruchomienie | 1,789 s. Wszystkie sześć plików zachowało bajty. |
| Dwie ewidencje i sprzątanie | Po zasileniu drugiego wyjścia osobnym skanem oba katalogi miały własny plik `owned`. Po usunięciu jednego wejściowego PDF-u oczyszczono wyłącznie jego JSON. Zachowano plik ręczny, pozostałe wyniki i osobną ewidencję drugiego wyjścia. |
| Izolacja wykonania | Obróbka działała z `network_mode: none` i `--pull never`. W kontenerze wykryto tylko interfejs `lo`. Próba zapisu do wejścia zwróciła `EROFS`. Katalog aplikacji zawierał pakiet CLI i dwa pliki zależności. |
| Regresja A | 7 testów, 0 błędów |

Pierwsza budowa wraz z pobraniem obrazu bazowego trwała 15,934 s. Pierwszy start ujawnił, że `ADD --chmod=0444` nadało ten tryb także tworzonemu katalogowi `/opt/tessdata`. Poprawka tworzy katalog wcześniej z prawami `0755`. Dodatkowa próba potwierdziła odczyt danych OCR i inicjalizację Tesseract dla UID 1000. Odbiór rootless użył UID 0 w kontenerze, które odpowiada UID właściciela montowanych katalogów na VPS.

Pomiar obejmuje środowisko Linux x86-64 na VPS. Budowa wymaga pobrania obrazu bazowego, zależności i polskich danych językowych. Logi wraz z pełnymi SHA-256 porównanych plików są w `~/uzp-parallel/compose-proof/full.IWVzFr/`.

## Powtórzenie z czystej kopii

Instrukcja jurora jest w [README](README.md). Z katalogu głównego czystej kopii gałęzi na VPS:

```sh
export PATH="$HOME/.local/bin:$PATH"
PROOF="$HOME/uzp-parallel/compose-proof"
RUN="$(mktemp -d "$PROOF/full.XXXXXX")"
"$PROOF/venv/bin/python" -m delivery.compose.verify "$RUN/run" \
  --dataset "$HOME/uzp-baseline-a/data/uzp" --tessdata "$PROOF/tessdata"
```

Polecenie przygotowuje wejście, uruchamia natywne CLI i `docker compose build cli`, wykonuje osobne `docker compose run --rm` i porównuje ścieżki, bajty oraz diagnostykę. Regresję uruchomiono przez `python -m unittest discover -s evaluation -p 'test_*.py'` w środowisku natywnego A.
