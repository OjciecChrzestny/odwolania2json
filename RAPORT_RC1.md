RC_SHA=1937848079584ec72aa1307f1305637e93607e1c

**Stan odbioru: zaliczony na VPS z czystego klonu.**

# Odbiór kandydata konkursowego A2

Przed pomiarem końcowym wybrano A2 z lokalnym polskim OCR. Przemawiają za tym dwa odzyskane syntetyczne przelewy oraz 128 identycznych bajtowo JSON-ów rozwojowych względem A. Przetwarzanie działa na CPU bez API. Walidacja 0,9878 z `valid_run=false` jest historycznym wynikiem oryginalnego A. [Raport A](RAPORT_A.md) · [Porównanie A2](RAPORT_A2.md)

| Identyfikator | Wartość |
| --- | --- |
| Pakiet `odwolania2json` | `a359032b4478d458090e68b1b3c85084138eac98` |
| Dane UZP | `de135d20811caf630f3e94dc655ba5eebd9a6710` |
| Projekt na VPS | `/home/dev-viralpay/uzp-parallel/rc1` |
| Dowody z odbioru | `/home/dev-viralpay/uzp-parallel/rc1-proof/acceptance.4PsV2H5A` |
| Linux i sprzęt | 6.8.0-31-generic x86-64, 6 vCPU Intel Xeon Gold 6258R @ 2,70 GHz, 23,46 GiB RAM |
| Runtime natywny i obraz | CPython 3.13.18, pypdf 6.21.4, pypdfium2 5.15.2, tesserocr 2.13.0 |
| Docker | Engine i klient 29.1.3, Compose 2.40.3, kontekst rootless |
| Obraz bazowy Pythona | `sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72` |
| Zbudowany obraz CLI na VPS | `sha256:ceeb1cc0b6f688c187759df952ed57d5e0c65aa98c328758cb3762d61238441a` |
| SHA-256 polskich danych OCR | `c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2` |

Historia wydania zawiera A2 `39805dd26c0443f5dcdcef837734897f843f4395`, oba commity pokazu `c01401cd7abdf82655b18188f68cb46652dc239e` i `72337e2164f871fa3b1d6c63edde0381b7ed8b31` oraz Compose `a2f5412a89a2ccfbfd9d91f19641df88a50f05a4`. Raporty źródłowe i miernik zachowano. [Odbiór źródłowy Compose](delivery/compose/RAPORT.md)

## Wyniki odbioru

| Próba | Obserwacja |
| --- | --- |
| Regresje CLI | 8 testów, wszystkie zaliczone |
| Natywnie i w Compose | 6/6 ścieżek, JSON-ów i diagnostyka identyczne, także przy domyślnych montowaniach |
| OCR i negatyw | Syntetyczny skan dał kwotę 123,45 i `ocr_pages=[1]`. Dokument obcy miał 0 bajtów. Dane OCR w obrazie zgadzały się z SHA-256. |
| Compose po powtórzeniu | Identyczne wyniki; pusty folder, niezależne ewidencje i usunięcie wyłącznie wygenerowanego wyniku po zmianie wejścia zaliczone. Kontener miał tylko interfejs `lo`, a montowanie wejścia było tylko do odczytu. |
| Dodanie klasy | 11/11 zgodnych ścieżek i sum SHA-256, 8/8 pustych negatywów. Zgodne pola, sygnały, strony i wskazane linie dokumentów syntetycznych. |
| Izolowany development | 128/128 wyników spełniło kontrakt i miało identyczne bajty jak A2. 1355 TP, 5 FP, 5 FN, ścisłe mikro-F1 0,9963235294, `valid_run=true`. |

Logi `tests.log`, `compose.log`, `extension.log` i `development.log` oraz metadane środowiska są w katalogu dowodów. Ekstraktor development działał na oddzielnej projekcji pakietu, neutralnym wejściu i z izolacją Landlock. Miernik uruchomiono osobno z `evaluation/development-40.json`.

## Polecenia odbioru

Z czystego klonu przypiętego do `RC_SHA` na Linuxie. `UZP_DATA` wskazuje dane na rewizji z tabeli. `TOOLS` zawiera venv Python 3.13, katalog `tessdata` i skompilowane narzędzie Landlock. `PROOF` oznacza osobny katalog dowodów, a `DEV` nowy katalog rozwojowy.

```sh
export PATH="$HOME/.local/bin:$PATH" DOCKER_CONTEXT=rootless
. "$TOOLS/venv/bin/activate"
python -m pip install --only-binary=:all: -r requirements.txt -r requirements-ocr.txt
cc -std=c11 -O2 -Wall -Wextra -Werror evaluation/restrict_linux.c -o "$TOOLS/restrict-linux"
python -m unittest discover -s evaluation -p 'test_*.py'
python demo/rozszerzalnosc/accept.py --work "$PROOF/extension" \
  --dataset "$UZP_DATA" --ocr-data "$TOOLS/tessdata" --restrict-linux "$TOOLS/restrict-linux"
python -m delivery.compose.verify "$PROOF/compose" --dataset "$UZP_DATA" --tessdata "$TOOLS/tessdata"
python evaluation/prepare_input.py "$UZP_DATA" evaluation/development-40.json "$DEV/input"
mkdir -p "$DEV/product"
git archive HEAD odwolania2json | tar -x -C "$DEV/product"
bash evaluation/run_private_linux.sh "$TOOLS" "$DEV/product" "$DEV"
python evaluation/score.py "$UZP_DATA" "$DEV/output" --manifest evaluation/development-40.json > "$DEV/score.json"
python -m evaluation.check_outputs "$DEV/output" --manifest evaluation/development-40.json \
  --diagnostics "$DEV/diagnostics/extraction.json" --score "$DEV/score.json"
```

Odbiór RC wykonano na VPS. Pomiar wydajności na laptopie jurora oraz pomiar końcowy mają osobne protokoły. Zakres tego przebiegu obejmował syntetyki i dane rozwojowe.
