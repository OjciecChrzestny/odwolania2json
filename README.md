# Odwołania2JSON

Odwołania2JSON przetwarza wielodokumentowe sprawy Krajowej Izby Odwoławczej. Dla każdego odwołania, pełnomocnictwa i potwierdzenia przelewu zapisuje osobny JSON w schemacie UZP. Typ dokumentu rozpoznaje po treści, więc nazwy nadane skanom nie wpływają na klasyfikację.

[Prezentacja techniczna (PDF, 7 slajdów)](docs/prezentacja.pdf) · [Własny PDF w panelu](docs/operator.md) · [Wydanie wdrożone na VM](https://github.com/OjciecChrzestny/odwolania2json/releases/tag/v2026.11.22-uzp-auto)

## Jak działa ekstrakcja

1. **Tekst i skany.** `pypdf` odczytuje warstwę tekstową każdej strony. Gdy potrzebny jest OCR, PDFium renderuje obraz, a Tesseract z polskim modelem rozpoznaje tekst lokalnie na CPU. Limit 6 stron OCR na PDF ogranicza koszt obliczeń długich skanów.
2. **Klasa i pola.** Klasyfikator sumuje wagi sygnałów, m.in. nagłówków i etykiet. Sprawdza próg klasy oraz warunki wykluczające, np. status oczekującej płatności. Reguły wybranej klasy odczytują m.in. identyfikator pierwszego zarzutu, mocodawcę i pełnomocników albo kwotę i datę operacji. Remis lub brak rozpoznania daje plik 0 B. [Definicje klas](odwolania2json/classes)
3. **Model dla jednego pola.** Jeżeli po lokalnym OCR pierwszej strony rozpoznanego przelewu brakuje kwoty, program może przekazać wycinki z cyframi i etykiety z zamkniętego słownika do Mistral Small 3.2 24B przez Scaleway. Błąd usługi pozostawia wynik lokalny. Panel i CLI dzielą limit **1 EUR na VM**, a trwała ewidencja zapobiega ponownemu wywołaniu dla tego samego pliku. [Sposób rozliczania prób](RUN.md)

## Jak sprawdzić wynik i rozszerzyć schemat

- **Dowód dla operatora.** W przykładzie przelewu pole `przelew_bankowy.kwota` ma wartość `123.45`. Panel pokazuje cytat „123,45”, numer strony i regułę odczytu. Operator otwiera tę stronę PDF-u, sprawdza czytelność i zapisuje akceptację lub korektę w osobnym dzienniku. [Pokaz na własnym PDF-ie](docs/operator.md)
- **Nowy typ i nowe pola.** Jeden plik JSON definiuje sygnały, próg, schemat i reguły odczytu. Na tym samym obrazie Dockera można w ten sposób dodać zawiadomienie oraz zagnieżdżony obiekt `miejsce_posiedzenia` z budynkiem i salą. W przykładzie brak numeru sali daje `null`, a podobne pismo obce daje 0 B. [Próba do samodzielnego odtworzenia](demo/rozszerzalnosc/README.md)

## Wyniki i zakres pomiaru

W wydaniu lokalnym `55afdb3c` mikro-F1 pól wyniósł **99,9265% na 128 rozwojowych PDF-ach** oraz **95,5372% na 30 publicznych skanach użytych do strojenia**. W odrębnej próbie 72 syntetycznych dokumentów klasyfikator pominął wszystkie 58 przelewów o nowych układach. Partia techniczna 150 różnych PDF-ów na 2 vCPU zakończyła się w 60,80 s. [Raport mierzonego wydania](https://github.com/OjciecChrzestny/odwolania2json/releases/tag/v2026.11.22-uzp) · [Opis miary i zbiorów](docs/jakosc.md)

## Uruchomienie na VM oceny

Włóż PDF-y do `/opt/solution/input/`. W katalogu `/opt/solution` wykonaj `./run-jury.sh`. Wyniki pojawią się w `output/` w tych samych podkatalogach, z nazwami plików wejściowych i rozszerzeniem `.json`. Wdrożone wydanie `bfec9183` przeszło próbę tej komendy jako administrator po restarcie VM. Wszystkie trzy wyniki były zgodne ze wzorcem w 1,67 s. Próba objęła tekstowy przelew, skan i dokument obcy. Dla wersji z automatycznym API nie powtarzaliśmy pełnego pomiaru F1. Wynik na tajnych sprawach określi jury. [RUN.md](RUN.md)

<details>
<summary>Instalacja programistyczna bez Dockera</summary>

### Środowisko Pythona

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

<a id="opcjonalny-ocr"></a>

### Instalacja polskiego OCR na Linuksie

CLI czyta warstwę tekstową każdej strony. Opcja `--ocr-max-pages N` ustala osobny budżet różnych stron poddanych OCR w jednym PDF-ie (domyślnie 6). Strona z tekstem nie zużywa budżetu. Brak wolnego miejsca na potrzebny OCR daje w diagnostyce `ocr_page_budget` dla nieocenionej strony. Rozpoznawanie klasy nadal korzysta z jej skonfigurowanych stron początkowych.

W osobnej instalacji programistycznej przygotuj zależności lokalnego OCR. Poniższe polecenia wykonaj na Linuksie w środowisku utworzonym powyżej. Koła binarne muszą być dostępne dla używanej wersji Pythona i architektury. Plik językowy jest przypięty do wydania `tessdata_fast` 4.1.0.

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

</details>

## Docker Compose

Wymagany jest Docker Engine z kontenerami linuksowymi i Compose v2. Compose uruchamia wcześniej przygotowany `odwolania2json-jury:auto-20261122` z polskim OCR. Na VM użyj polecenia z RUN.md. [Przygotowanie i weryfikacja obrazu](RUN.md#przygotowanie-obrazu-przed-oceną) Domyślny użytkownik kontenera jest wspólny z `RUN.md`. W trybie rootless odpowiada użytkownikowi demona na hoście.

```sh
mkdir -p input output diagnostics .output.odwolania2json
# Wstaw PDF-y do input/ przed uruchomieniem usługi.
docker compose run --rm --pull never -e OMP_THREAD_LIMIT=1 cli
```

[Compose z własnymi katalogami oraz instrukcja dla Windows](delivery/compose/README.md)

## Obraz do eksperymentów deweloperskich

Zadania z adapterami można spakować osobno. Obraz zawiera kod weryfikacji przelewów, adaptery B/C i kod odczytu pól przelewu. Punkt wejścia i lokalna ekstrakcja zachowują dotychczasowe działanie.

```sh
docker build --target adapters --tag odwolania2json:adapters .
```

Budowa obejmuje wyłącznie potrzebne moduły i zależności. Dane, pliki referencyjne i `.env` są poza obrazem. Użyj tego celu po wyborze adaptera i uzgodnieniu konfiguracji sieciowej. Komenda oceny w `RUN.md` automatycznie obsługuje kwalifikujące się brakujące kwoty. [Weryfikator przelewów i pomiary](experiments/transfer_api/RAPORT_KLASYFIKACJA.md) · [Adaptery B/C](experiments/abc/README.md)

## Reguły i rozszerzanie

Domyślne konfiguracje to `odwolanie.json`, `pelnomocnictwo.json` i `przelew.json`. Definicje klas zawierają punktowane sygnały, próg rozpoznania, schemat, wzorce pól i operacje normalizacji. Brak kandydata spełniającego próg lub remis daje wynik dokumentu obcego. Pierwsza reguła pola, która daje poprawną wartość, wygrywa. Do prostych klas wystarczy własny plik JSON z unikatową nazwą `class`, listą `signals`, progiem `threshold`, obiektem `schema` i mapą `fields`. Reguła pola używa pierwszej grupy przechwytującej i opcjonalnej operacji, np. `date` z symbolem `<DATE>`. Pole opisane jako `date?` przyjmuje datę ISO lub `null`. Przykład niezależnej klasy z dwoma polami jest w `ExtensionTest`. [Katalog konfiguracji klas](odwolania2json/classes)

Sygnał klasy może mieć opcjonalną mapę `requires`. Każdy nazwany wzorzec z mapy musi pasować na tej samej stronie co wzorzec główny. Diagnostyka zapisuje nazwy spełnionych warunków w `criteria`. W klasie przelewu ustawienie `retry_ocr` przy sygnale nagłówka pozwala ponownie odczytać układ pierwszej strony skanu. Oba odczyty obowiązują te same kryteria rozpoznania.

Opcja `--config KATALOG` wybiera cały katalog klas. Skopiuj do niego klasy UZP, jeśli mają działać obok nowej. Sekcje prawne korzystają dodatkowo ze wspólnych operacji na fragmentach tekstu i konfigurowalnych wzorców ról. Słownik powodów odwołania jest przypięty w konfiguracji. Gdy brak wiarygodnej daty pierwszej czynności, wynikiem jest `null`. Gdy żadna reguła nie przypisze rodzaju czynności, konfiguracja wymusza ID 11, a diagnostyka oznacza `first_allegation.fallback=true`.

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

## Dowody i materiały

- [Próba jurora](delivery/final/INSTRUKCJA-JURORA.md) i [scenariusz finału](delivery/final/SCENARIUSZ.md).
- [Odbiór Compose](delivery/compose/README.md) i [próba dodania klasy](demo/rozszerzalnosc/README.md).
- [Historia i dotychczasowe pomiary](docs/historia/README.md). Wyniki odnoszą się do wskazanych rewizji i zbiorów.
