# Wariant A — pomiar na VPS

Pomiar wykonano 21 listopada 2026 r. na 32 PDF-ach z 10 zamrożonych spraw walidacyjnych. Ekstrakcja zapisała 32 wyniki i zakończyła się kodem 0. Ścisłe mikro-F1 wyniosło **0,9878048780**. Miernik zwrócił **`valid_run=false`**, ponieważ jeden przelew został sklasyfikowany jako dokument obcy. Pomiar wykonano raz. Utrwalony wynik obejmuje ten błąd klasyfikacji.

| Identyfikator | Wartość |
| --- | --- |
| Gałąź na VPS | `codex/uzp-baseline-a` |
| SHA mierzonej implementacji | `19f702fc58e685f85f2fae14557d14f2c5453cfd` |
| Drzewo Git konfiguracji klas | `4d9ebc4e3d71668a6e388eaf813d34fc2c31b5ff` |
| Rewizja danych organizatora | `de135d20811caf630f3e94dc655ba5eebd9a6710` |
| Python i biblioteki | CPython 3.13.18, pypdf 6.21.4, pypdfium2 5.15.2, tesserocr 2.13.0 |
| Sprzęt | 6 vCPU, Intel Xeon Gold 6258R @ 2,70 GHz, 24 600 288 KiB RAM (23,46 GiB), 128 GiB wolnego miejsca |
| Pomiar ekstrakcji | GNU `/usr/bin/time -v`, 1,42 s czasu ściennego, szczyt RSS 45 676 KiB (44,61 MiB) |
| Tryb | Linux 6.8.0-31-generic, CPU, osobny venv, włączony lokalny OCR z przypiętym `pol.traineddata` |
| Projekt na VPS | `/home/dev-viralpay/uzp-baseline-a/project` |
| Czysta kopia pomiarowa | `/home/dev-viralpay/uzp-baseline-a/runs/rehearsal/clean` |
| Prywatny zapis walidacji | `/home/dev-viralpay/uzp-baseline-a/runs/validation-a` |

Pomiar czasu i RSS obejmuje proces publicznego CLI uruchomiony przez Landlock. Przygotowanie wejścia, F1 i walidacja struktury działały w innych procesach. Izolację sprawdzono próbą odczytu poza dozwolonym drzewem i próbą połączenia TCP. Projekcja mierzona przez CLI zawierała pakiet z konfiguracją, a wejście składało się z neutralnie nazwanych PDF-ów.

## Wynik walidacyjny

| Klasa wzorcowa | PDF-y | TP | FP | FN | Ścisłe mikro-F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Odwołanie | 10 | 193 | 1 | 1 | 0,9948453608 |
| Pełnomocnictwo | 10 | 77 | 0 | 0 | 1,0000 |
| Przelew | 10 | 54 | 0 | 6 | 0,9473684211 |
| Dokument obcy | 2 | 0 | 0 | 0 | — |
| **Łącznie** | **32** | **324** | **1** | **7** | **0,9878048780** |

Macierz ma wiersze z klasy wzorcowej dostępnej ocenie i kolumny z klasy zapisanej przez ekstraktor przed oceną.

| Wzorzec ↓ / predykcja → | Odwołanie | Pełnomocnictwo | Przelew | Dokument obcy |
| --- | ---: | ---: | ---: | ---: |
| Odwołanie | 10 | 0 | 0 | 0 |
| Pełnomocnictwo | 0 | 10 | 0 | 0 |
| Przelew | 0 | 0 | 9 | 1 |
| Dokument obcy | 0 | 0 | 0 | 2 |

- ID pierwszej czynności trafione w **10/10** odwołań. Użycia awaryjnego ID **0**.
- Fałszywe rozpoznania na dokumentach obcych **0/2**. Oba pliki mają 0 bajtów.
- Walidator struktury zwrócił `valid_contract=true` i 0 błędów ścieżek, typów i schematów według klas przewidzianych. **31/32** plików miało format zgodny także z klasą wzorcową. `case_27/doc_03.json` ma 0 bajtów, choć wzorzec oczekuje obiektu przelewu. Niezmieniony `score.py` zakończył się kodem 1 i błędem `Expecting value: line 1 column 1 (char 0)`.
- Błędy odczytu i dokumenty wymagające OCR w walidacji **0/32**. OCR rozpoznawał tekst w 3 dokumentach rozwojowych bez warstwy tekstowej.
- Szczegóły są w `score.json`, `contract.json`, `diagnostics/extraction.json`, `time.txt` i `metadata.txt` w prywatnym katalogu przebiegu, obok jego drzew wejścia i wyjścia.

## Odbiór i odtworzenie

Czysty checkout z nowym środowiskiem przeszedł 7 testów. Pierwszy przelew `case_01/doc_02.pdf` powtórzony pod inną nazwą dał identyczne bajty. Zgodne są `data_operacji`, liczbowa `kwota`, `tytul`, `numer_transakcji`, `z_rachunku` i `na_rachunek`. Rachunki zachowały typ tekstowy i przypisanie do ról. Pełna sprawa, wieloosobowe pełnomocnictwo, dokument obcy, dwie instancje klasy, pusty katalog, powtórzenie i sprzątanie przeszły odbiór. Skan bez czytelnej treści oraz uszkodzony PDF zakończyły się jawnym statusem błędu i CLI przetworzyło następne pliki w teście regresji.

`check_splits.py` potwierdził 191 unikatowych PDF-ów, 180 referencji i zerowe przecięcia spraw, hashy PDF i hashy etykiet w każdej parze. Zbiór końcowy przeszedł wyłącznie tę kontrolę. SHA-256 manifestu końcowego po normalizacji LF to `f36fffc9127520e0caad2df4413a2e6769b2b4d9e2dc1de5de9c668e9efa0a8b`.

Przebieg rozwojowy tego samego SHA znajduje się w `runs/development-frozen` na VPS. Jego 128/128 plików spełniło kontrakt, `valid_run=true`, a wynik to 1355 TP, 5 FP, 5 FN i mikro-F1 0,9963235294.

Polecenia wykonane z czystej kopii na VPS. W poleceniach przygotowania i oceny `RUN` oznacza bezwzględną ścieżkę nowego przebiegu, a `MANIFEST` ścieżkę wybranego manifestu. Przechowywany przebieg walidacji pozostaje punktem odniesienia A.

```sh
ROOT=/home/dev-viralpay/uzp-baseline-a
TOOLS="$ROOT/runs/rehearsal/tools"
export UZP_DATA="$ROOT/data/uzp"
. "$TOOLS/venv/bin/activate"
python --version
git rev-parse HEAD
git rev-parse HEAD:odwolania2json/classes
git -C "$UZP_DATA" rev-parse HEAD
python -m pip install -r requirements.txt
python -m pip install --only-binary=:all: -r requirements-ocr.txt
python evaluation/check_splits.py "$UZP_DATA"
python -m unittest discover -s evaluation -p 'test_*.py'
python evaluation/accept_development.py "$UZP_DATA" "$ROOT/runs/rehearsal/acceptance"
cc -std=c11 -O2 -Wall -Wextra -Werror evaluation/restrict_linux.c -o "$TOOLS/restrict-linux"
python evaluation/prepare_input.py "$UZP_DATA" "$MANIFEST" "$RUN/input"
mkdir -p "$RUN/product"
git archive HEAD odwolania2json | tar -x -C "$RUN/product"
bash evaluation/run_private_linux.sh "$TOOLS" "$RUN/product" "$RUN"
python evaluation/score.py "$UZP_DATA" "$RUN/output" --manifest "$MANIFEST" > "$RUN/score.json"
python -m evaluation.check_outputs "$RUN/output" --manifest "$MANIFEST" \
  --diagnostics "$RUN/diagnostics/extraction.json" --score "$RUN/score.json" > "$RUN/contract.json"
```

Dla rozwoju użyto `evaluation/development-40.json`, a dla walidacji `evaluation/validation-10.json`. Katalogi dla przygotowania wejścia i odbioru muszą być nowe przy odtwarzaniu.

**Ograniczenie.** Reguły zależą od nagłówków i etykiet obecnych w warstwie tekstowej. W walidacji błędne rozpoznanie jednego przelewu kosztowało sześć pól i ważność przebiegu w mierniku. PDF-y z istotną treścią po szóstej stronie i skany o słabej jakości pozostają ograniczeniem. Czas i RSS zmierzono na VPS.

**Następny krok.** Uruchomić zaplanowany wariant B z Qwen3.5-9B na walidacji z tym samym wyborem fragmentu i porównać zmianę ID oraz mikro-F1 z zachowanym przebiegiem A.
