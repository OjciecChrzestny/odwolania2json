# Jeden wewnętrzny pomiar końcowy A2

21 listopada 2026 r., godz. 16:55 CET. Ekstraktor przetworzył **10 spraw i 31 PDF-ów**, zapisał 31 wyników i zakończył się kodem 0. Ścisłe mikro-F1 wyniosło **0,9821958457** przy **`valid_run=false`**. Walidator struktury zwrócił **`valid_contract=true`**. Jedno pełnomocnictwo otrzymało klasyfikację dokumentu obcego.

| Identyfikator | Wartość |
| --- | --- |
| Mierzony commit `RC_SHA` | `1937848079584ec72aa1307f1305637e93607e1c` |
| Drzewo pakietu `odwolania2json` | `a359032b4478d458090e68b1b3c85084138eac98` |
| Decyzja o zamrożeniu | `747800f5a536967614686fb6f6210de48e6ce7c3`, raport `RAPORT_RC1.md` |
| Gałąź późniejszego raportu | `codex/uzp-pomiar-koncowy` |
| Rewizja danych UZP | `de135d20811caf630f3e94dc655ba5eebd9a6710` |
| SHA-256 `evaluation/final-10.json` po normalizacji LF | `f36fffc9127520e0caad2df4413a2e6769b2b4d9e2dc1de5de9c668e9efa0a8b` |
| Host | VPS `hacknation`, Ubuntu 24.04 LTS, Linux 6.8.0-31-generic, x86-64, 6 vCPU i 23,46 GiB RAM |
| Środowisko | Python 3.13.18, pypdf 6.21.4, pypdfium2 5.15.2, tesserocr 2.13.0, RootlessKit 1.1.1 |
| SHA-256 `pol.traineddata` | `c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2` |
| Czas ścienny partii i szczyt RSS | 1,27 s i 47 844 KiB (46,72 MiB), GNU `time -v` |
| Kody wyjścia | Ekstrakcja 0, `score.py` 1, `check_outputs` 0 |
| Prywatny przebieg | `/home/dev-viralpay/uzp-parallel/odbior-koncowy-prywatne/holdout-final-10` |

Przed rezerwacją katalogu sprawdzono decyzję w raporcie RC, plan i poprzednie katalogi przebiegów. Udokumentowane przebiegi obejmowały rozwój i walidację. Na rozwoju zamrożona procedura odtworzyła 128/128 wyników kontraktowych, 1355 TP, 5 FP i 5 FN. Próba błędu z uszkodzonym PDF-em i syntetycznym skanem zapisała kody 1/1/1 i odtworzyła polski tekst oraz kwotę dziesiętną. Próba izolacji potwierdziła odmowę dostępu do plików poza listą Landlock i blokadę TCP. Osobna przestrzeń sieciowa miała tylko interfejs `lo` bez trasy UDP.

## Wynik według klasy wzorcowej

| Klasa | PDF-y | Zgodna klasa | TP | FP | FN | Ścisłe mikro-F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Odwołanie | 10 | 10 | 207 | 2 | 3 | 0,9880668258 |
| Pełnomocnictwo | 10 | 9 | 64 | 0 | 7 | 0,9481481481 |
| Przelew | 10 | 10 | 60 | 0 | 0 | 1,0000000000 |
| Dokument obcy | 1 | 1 | 0 | 0 | 0 | — |
| **Łącznie** | **31** | **30** | **331** | **2** | **10** | **0,9821958457** |

Wszystkie **31/31** wyników spełniło kontrakt swojej przewidzianej klasy. **30/31** wyników miało poprawną klasę i spełniło kontrakt klasy wzorcowej. Błędnie sklasyfikowane pełnomocnictwo dało plik 0 B i 7 FN. Miernik zgłosił jeden błąd parsowania, ponieważ dla tego dokumentu oczekiwał obiektu JSON. Trafiono **9/10** ID pierwszej czynności i raz użyto ID awaryjnego. Liczba błędnie dodatnich dokumentów obcych wyniosła **0/1**. Jedyny wzorcowy dokument obcy dał plik 0 B. Błędy odczytu i użycie OCR w holdoucie wyniosły **0/31**. Skuteczność OCR sprawdzono wcześniej na syntetyku.

## Wykonane polecenia i odbiór

Użyto odrębnego czystego klonu na wskazanym `RC_SHA`. Przed przygotowaniem PDF-ów `mkdir -m 700` zarezerwował trwały katalog przebiegu. Osobny katalog `attempt/` zarezerwował jedną próbę ekstrakcji. Poniższy zapis pokazuje polecenia pomiaru wykonane kolejno w tym klonie. Kody zapisywano indywidualnie, więc ocena struktury odbyła się także po kodzie 1 miernika.

```sh
cd "$HOME/uzp-parallel/odbior-koncowy"
RC_SHA=1937848079584ec72aa1307f1305637e93607e1c
PROOF="$HOME/uzp-parallel/odbior-koncowy-prywatne"
TOOLS="$PROOF/tools"
RUN="$PROOF/holdout-final-10"
DATA="$HOME/uzp-baseline-a/data/uzp"
MANIFEST=evaluation/final-10.json
PYTHON="$TOOLS/venv/bin/python"

cc -std=c11 -O2 -Wall -Wextra -Werror evaluation/restrict_linux.c -o "$TOOLS/restrict-linux"
mkdir -m 700 "$RUN"
mkdir "$RUN/product"
git archive "$RC_SHA" odwolania2json | tar -x -C "$RUN/product"
"$PYTHON" -B evaluation/prepare_input.py "$DATA" "$MANIFEST" "$RUN/input"
mkdir "$RUN/attempt"
/usr/bin/env -i PATH=/usr/bin:/bin /usr/bin/rootlesskit -- /usr/bin/unshare --net -- \
  /usr/bin/bash evaluation/run_private_linux.sh "$TOOLS" "$RUN/product" "$RUN" \
  </dev/null > "$RUN/extraction.log" 2>&1
"$PYTHON" -B evaluation/score.py "$DATA" "$RUN/output" --manifest "$MANIFEST" \
  > "$RUN/score.json" 2> "$RUN/score.err"
"$PYTHON" -B -m evaluation.check_outputs "$RUN/output" --manifest "$MANIFEST" \
  --diagnostics "$RUN/diagnostics/extraction.json" --score "$RUN/score.json" \
  > "$RUN/contract.json" 2> "$RUN/contract.err"
```

`metadata.txt`, `time.txt`, `status.txt`, `score.json`, `contract.json` i szczegóły wyjścia są w prywatnym katalogu VPS. Odbiór istniejącego pomiaru odczytuje zapisane agregaty:

```sh
ssh hacknation 'cat ~/uzp-parallel/odbior-koncowy-prywatne/holdout-final-10/summary.json'
```
