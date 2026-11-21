# Odwołania2JSON

Lokalny wariant regułowy A dla zadania UZP na HackNation 2026. Rozpoznaje odwołanie, pełnomocnictwo, przelew i dokument obcy. Po instalacji działa na CPU bez sieci i kluczy API.

## Instalacja i własne PDF-y

Wymagany jest Python 3.13 lub nowszy. Z katalogu repozytorium na Linuxie:

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
mkdir -p input
# Kopiuj PDF-y do input/ lub jego podkatalogów.
python -m odwolania2json
```

W PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
New-Item -ItemType Directory -Path input -Force | Out-Null
# Kopiuj PDF-y do input\ lub jego podkatalogów.
.\.venv\Scripts\python.exe -m odwolania2json
```

Wejście `input/sprawa/pismo.pdf` daje `output/sprawa/pismo.json`. Dla dokumentu obcego plik ma dokładnie 0 bajtów. Dla błędu odczytu CLI pomija wynik tego PDF-u, zapisuje status `read_error`, kończy pozostałe dokumenty i zwraca kod 1. Kod 2 sygnalizuje błąd konfiguracji lub operacji na drzewie. Powtórny bieg usuwa przestarzałe wyniki zapisane w ewidencji obok drzewa (domyślnie `.output.odwolania2json/`). Samodzielnie dodane pliki pozostają na miejscu. Aby zacząć nowy przebieg, wskaż nowy katalog przez `--output`.

Diagnostyka w `diagnostics/last-run.json` zapisuje klasę przed oceną, status, strony OCR oraz regułę i numer strony dla wydobytego pola. Inne katalogi wejściowe i wyjściowe oraz ścieżkę diagnostyki można wskazać jawnie:

```sh
python -m odwolania2json --input moje-pdf --output wyniki \
  --diagnostics diagnostyka/przebieg.json
```

### Opcjonalny OCR

Użyj na Linuxie z Pythonem 3.13. OCR zadziała lokalnie po zapisaniu polskich danych językowych. A wywołuje go przy braku warstwy tekstowej na początku PDF-u.

```sh
python -m pip install --only-binary=:all: -r requirements-ocr.txt
mkdir -p /bezwzgledna/sciezka/tessdata
curl -fsSL https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/pol.traineddata \
  -o /bezwzgledna/sciezka/tessdata/pol.traineddata
sha256sum /bezwzgledna/sciezka/tessdata/pol.traineddata
python -m odwolania2json --ocr-data /bezwzgledna/sciezka/tessdata
```

Oczekiwany SHA-256 danych językowych to `c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2`. Komponenty to pypdf, opcjonalnie PDFium przez pypdfium2 oraz Tesseract przez tesserocr.

## Reguły i rozszerzanie

Definicje klas w [katalogu konfiguracji](odwolania2json/classes) zawierają punktowane sygnały, próg rozpoznania, schemat, wzorce pól i operacje normalizacji. Pierwsza reguła pola, która daje poprawną wartość, wygrywa. Do prostych klas wystarczy własny plik JSON z unikatową nazwą `class`, listą `signals`, progiem `threshold`, obiektem `schema` i mapą `fields`. Reguła pola używa pierwszej grupy przechwytującej i opcjonalnej operacji, np. `date` z symbolem `<DATE>`. Pole opisane jako `date?` przyjmuje datę ISO lub `null`. Przykład niezależnej klasy z dwoma polami jest w `ExtensionTest`.

Opcja `--config KATALOG` wybiera cały katalog klas. Skopiuj do niego klasy UZP, jeśli mają działać obok nowej. Sekcje prawne korzystają dodatkowo ze wspólnych operacji na fragmentach tekstu i konfigurowalnych wzorców ról. Słownik powodów odwołania jest przypięty w konfiguracji. Gdy brak wiarygodnej daty pierwszej czynności, wynikiem jest `null`. Gdy żadna reguła nie przypisze rodzaju czynności, konfiguracja wymusza ID 11, a diagnostyka oznacza `first_allegation.fallback=true`. Odczyt obejmuje maksymalnie sześć pierwszych stron.

## Testy

Podstawowe testy działają na syntetycznych przykładach po instalacji `requirements.txt`.

```sh
python -m unittest discover -s evaluation -p 'test_*.py'
```

Przy osobnej kopii [przypiętych danych UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/de135d20811caf630f3e94dc655ba5eebd9a6710):

```sh
export UZP_DATA=/bezwzgledna/sciezka/do/hacknation-2026
git -C "$UZP_DATA" rev-parse HEAD
python evaluation/check_splits.py "$UZP_DATA"
python evaluation/accept_development.py "$UZP_DATA" runs/odbior-a
```

Odbiór przelewu porównuje wszystkie pola z rozwojową referencją dopiero po uruchomieniu publicznego CLI. Kolejna próba obejmuje pełną sprawę, wieloosobowe pełnomocnictwo, dokument obcy, powtórne uruchomienie, zmianę ścieżek i usuwanie starych wyników. Polecenie wymaga nowej ścieżki przebiegu.

[Plan testów A/B/C i zamrożony podział](PLAN.md) · [Raport pomiaru A](RAPORT_A.md)
