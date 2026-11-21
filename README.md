# Odwołania2JSON

Odwołania2JSON rozpoznaje odwołania KIO, pełnomocnictwa i potwierdzenia przelewów. Dla dokumentów obcych zapisuje plik 0 B. Wariant A3 stosuje reguły i lokalny polski OCR na CPU. Przetwarzanie działa bez sieci, GPU i klucza API.

[Instrukcja jurora od czystej kopii z własnym PDF-em](delivery/final/INSTRUKCJA-JURORA.md)

## Instalacja i własne PDF-y

Wymagany jest Python 3.13 lub nowszy. Przy pierwszej instalacji pip pobiera zależności. Poniższe polecenia uruchom z katalogu głównego repozytorium na Linuksie.

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

Diagnostyka w `diagnostics/last-run.json` zapisuje status, przypisaną klasę, strony poddane OCR oraz regułę i numer strony dla wydobytego pola. Ścieżki można wskazać jawnie. Użyj odrębnych katalogów wejściowych, wyjściowych i diagnostycznych.

```sh
python -m odwolania2json --input moje-pdf --output wyniki \
  --diagnostics diagnostyka/przebieg.json
```

### Opcjonalny OCR

Do dokumentów skanowanych włącz polski OCR lub użyj Compose. Poniższe polecenia wykonaj na Linuksie w środowisku utworzonym powyżej. Koła binarne muszą być dostępne dla używanej wersji Pythona i architektury. Plik językowy jest przypięty do wydania `tessdata_fast` 4.1.0.

```sh
python -m pip install --only-binary=:all: -r requirements-ocr.txt
TESSDATA="$PWD/.venv/tessdata"
mkdir -p "$TESSDATA"
curl -fsSL https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/pol.traineddata \
  -o "$TESSDATA/pol.traineddata"
printf '%s  %s\n' c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2 \
  "$TESSDATA/pol.traineddata" | sha256sum -c -
```

Po potwierdzeniu sumy uruchom OCR na domyślnych katalogach:

```sh
OMP_THREAD_LIMIT=1 python -m odwolania2json --ocr-data "$TESSDATA"
```

A3 odczytuje przez OCR wybrane strony, gdy brakuje czytelnej warstwy tekstowej. Odczyt używa pypdf, a OCR korzysta z PDFium przez pypdfium2 i z Tesseract przez tesserocr. [Pochodzenie i licencje komponentów](delivery/final/INSTRUKCJA-JURORA.md#komponenty-zewnętrzne)

## Docker Compose

Wymagany jest Docker Engine z kontenerami linuksowymi, Compose v2 i BuildKit. Budowa obrazu pobiera zależności. Kontener uruchamia A3 z polskim OCR i ma wyłączoną sieć. W trybie rootless po ustawieniu identyfikatorów z przykładu wykonaj `export ODW_UID=0 ODW_GID=0` przed uruchomieniem kontenera.

```sh
mkdir -p input output diagnostics .output.odwolania2json
export ODW_UID="$(id -u)" ODW_GID="$(id -g)"
# Wstaw PDF-y do input/ przed uruchomieniem usługi.
docker compose build cli
docker compose run --rm --pull never -e OMP_THREAD_LIMIT=1 cli
```

[Compose z własnymi katalogami oraz instrukcja dla Windows](delivery/compose/README.md)

## Reguły i rozszerzanie

Domyślne konfiguracje to `odwolanie.json`, `pelnomocnictwo.json` i `przelew.json`. Definicje klas zawierają punktowane sygnały, próg rozpoznania, schemat, wzorce pól i operacje normalizacji. Brak kandydata spełniającego próg lub remis daje wynik dokumentu obcego. Pierwsza reguła pola, która daje poprawną wartość, wygrywa. Do prostych klas wystarczy własny plik JSON z unikatową nazwą `class`, listą `signals`, progiem `threshold`, obiektem `schema` i mapą `fields`. Reguła pola używa pierwszej grupy przechwytującej i opcjonalnej operacji, np. `date` z symbolem `<DATE>`. Pole opisane jako `date?` przyjmuje datę ISO lub `null`. Przykład niezależnej klasy z dwoma polami jest w `ExtensionTest`. [Katalog konfiguracji klas](odwolania2json/classes)

Sygnał klasy może mieć opcjonalną mapę `requires`. Każdy nazwany wzorzec z mapy musi pasować na tej samej stronie co wzorzec główny. Diagnostyka zapisuje nazwy spełnionych warunków w `criteria`. W klasie przelewu ustawienie `retry_ocr` przy sygnale nagłówka pozwala ponownie odczytać układ pierwszej strony skanu. Oba odczyty obowiązują te same kryteria rozpoznania.

Opcja `--config KATALOG` wybiera cały katalog klas. Skopiuj do niego klasy UZP, jeśli mają działać obok nowej. Sekcje prawne korzystają dodatkowo ze wspólnych operacji na fragmentach tekstu i konfigurowalnych wzorców ról. Słownik powodów odwołania jest przypięty w konfiguracji. Gdy brak wiarygodnej daty pierwszej czynności, wynikiem jest `null`. Gdy żadna reguła nie przypisze rodzaju czynności, konfiguracja wymusza ID 11, a diagnostyka oznacza `first_allegation.fallback=true`. Odczyt obejmuje maksymalnie sześć pierwszych stron.

Pokaz dodania klasy `zawiadomienie` obejmuje dwa syntetyczne PDF-y, negatyw oraz sposób wskazania strony i reguły dla pola. Profil demonstracyjny dodaje jeden plik JSON. [Próba jurora i odbiór rozszerzenia](demo/rozszerzalnosc/README.md)

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

## Wybór kandydata i pomiary

A3 uzyskał mikro-F1 0,9963 na 128 rozwojowych PDF-ach, z prawidłowym przebiegiem i 40/40 poprawnych ID. Wszystkie pliki wynikowe miały te same bajty co w A2. Dwie zmiany nazw i katalogów dla każdego wejścia dały 256/256 zgodnych wyników i rekordów diagnostyki z pominięciem ścieżki. To wynik historyczny na zbiorze rozwojowym. Odrębna historyczna próba A3 na skanach ujawniła błędy klasyfikacji przelewów. [Odbiór A3](RAPORT_A3.md) · [Raport historycznej próby na skanach](RAPORT_KONCOWY_A3.md)

Wcześniejsza walidacja A dała mikro-F1 0,9878 z `valid_run=false`. Warianty B i C to oddzielne eksperymenty z wyborem ID pierwszego zarzutu, sprawdzone na atrapach z zablokowanym TCP. Domyślne CLI i obraz Compose pracują bez API. [Aktualne warunki UZP dla wariantu z API](delivery/final/INSTRUKCJA-JURORA.md#warunki-użycia-api) · [Raport A](RAPORT_A.md) · [Eksperyment B/C](experiments/abc/README.md) · [Plan i podział danych](PLAN.md)

[Odbiór historycznego RC1](RAPORT_RC1.md)

## Materiały przekazania

[Instrukcja jurora](delivery/final/INSTRUKCJA-JURORA.md) · [Prezentacja PDF](delivery/final/prezentacja.pdf) · [Ekrany rezerwowe](delivery/final/ekrany-rezerwowe.pdf) · [Scenariusz finału](delivery/final/SCENARIUSZ.md) · [Raport próby](delivery/final/RAPORT-PROBY.md)

Jeden wewnętrzny pomiar końcowy objął 31 PDF-ów na zamrożonym A2 z lokalnym OCR. Miernik zwrócił 0,9821958457 mikro-F1 oraz `valid_run=false` po sklasyfikowaniu jednego pełnomocnictwa jako dokumentu obcego. [Raport końcowy](RAPORT_KONCOWY.md)
