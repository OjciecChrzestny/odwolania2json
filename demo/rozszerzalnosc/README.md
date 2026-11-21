# Pokaz dodania klasy zawiadomienie

Uruchom z katalogu głównego projektu w Pythonie 3.13+ z zainstalowanym `requirements.txt`. Pokaz na syntetykach i własnym PDF-ie z warstwą tekstową działa lokalnie. Odbiór rozwojowy dodatkowo używa `requirements-ocr.txt` i polskich danych Tesseract zgodnie z [README projektu](../../README.md).

## Próba jurora

Poniższe komendy przygotowują dwa fikcyjne zawiadomienia, podobny dokument obcy i kopię trzech klas konkursowych w nowym katalogu.

```sh
DEMO=demo/rozszerzalnosc
WORK="$(mktemp -d)/pokaz"
python "$DEMO/pokaz.py" przygotuj "$WORK"

python -m odwolania2json --input "$WORK/input" --output "$WORK/domyslne" \
  --diagnostics "$WORK/diagnostics/domyslne.json"
wc -c "$WORK/domyslne/"*.json

cp "$DEMO/zawiadomienie.json" "$WORK/klasy/"
python -m odwolania2json --input "$WORK/input" --output "$WORK/demo" \
  --config "$WORK/klasy" --diagnostics "$WORK/diagnostics/demo.json"
cat "$WORK/demo/doc_01.json" "$WORK/demo/doc_02.json"
wc -c "$WORK/demo/doc_03.json"
python "$DEMO/pokaz.py" zrodlo "$WORK/input/doc_01.pdf" "$WORK/diagnostics/demo.json"
```

Otwórz `$WORK/input/doc_01.pdf` w lokalnej przeglądarce PDF. Na pierwszej stronie widnieje `Sygnatura: KIO-DEMO/17/26`. Na drugiej znajdziesz `Termin: 3 grudnia 2026`. Diagnostyka wskazuje stronę 2 i regułę `wiersz_terminu`. W wynikowym JSON-ie termin ma postać `2026-12-03`. Drugi PDF używa etykiet „Sygnatura akt” i „Termin posiedzenia”, a wynikowa data to `2027-01-18`. Obce pismo ma etykiety obu pól, lecz inny nagłówek. Jego wynik ma 0 bajtów.

Aby sprawdzić własny PDF, skopiuj go do osobnego wejścia i uruchom ten sam profil. Przykładowe etykiety możesz wpisać we własnym edytorze i wyeksportować jako PDF. Użyj nagłówka „ZAWIADOMIENIE” w osobnym wierszu oraz „Sygnatura:” lub „Sygnatura akt:” na jednej z dwóch pierwszych stron. Obsługiwane etykiety daty to „Termin:” i „Termin posiedzenia:”. Jeśli dokument ma inny układ, dopasuj wzorce w kopii `$WORK/klasy/zawiadomienie.json`.

```sh
mkdir "$WORK/juror"
cp "/ścieżka/do/własnego.pdf" "$WORK/juror/wlasny.pdf"
python -m odwolania2json --input "$WORK/juror" --output "$WORK/wynik-jurora" \
  --config "$WORK/klasy" --diagnostics "$WORK/diagnostics/juror.json"
cat "$WORK/wynik-jurora/wlasny.json"
python "$DEMO/pokaz.py" zrodlo "$WORK/juror/wlasny.pdf" "$WORK/diagnostics/juror.json"
```

## Od klasy do źródła pola

1. `--config` wskazuje katalog profilu. `model.load_classes` wczytuje wszystkie jego pliki JSON i sprawdza unikatowość nazw klas. Konfiguracja fabryczna zawiera trzy klasy.
2. Klasyfikator sprawdza nagłówek i etykietę sygnatury w pierwszych dwóch stronach. Sygnały dają 4 i 2 punkty przy progu 6. Diagnostyka przechowuje nazwy i strony trafionych sygnałów. Wspólny klasyfikator wybiera najwyższy wynik. Remis kończy się dokumentem obcym.
3. Reguła pola bierze pierwszą grupę przechwytującą. `text` porządkuje odstępy sygnatury, a operacja `date` zamienia datę opisową lub liczbową na ISO. Schemat dopuszcza `null` przy braku poprawnego odczytu.
4. Ekstraktor przypisuje pozycję dopasowanej wartości do numeru strony PDF liczonego od 1. JSON wyjściowy zawiera pola, a osobna diagnostyka zapisuje `fields.<pole>.page` i `fields.<pole>.rule`. Komenda `zrodlo` otwiera tę samą stronę wejściowego PDF-u i wypisuje jej tekst.

Próba obejmuje układy pokazane powyżej. Treść po szóstej stronie jest poza zakresem czytnika. Wynik zależy od warstwy tekstowej, a skany wymagają opcjonalnego OCR. Czytaj diagnostykę razem z dokumentem. Wskazanie obejmuje stronę, bez współrzędnych na stronie.

## Odbiór z czystej kopii

Uruchom na VPS z rozgrzanego środowiska. Ustaw `UZP_DATA` na przypiętą kopię UZP i `OCR_DATA` na katalog z `pol.traineddata`. Opcjonalny izolator Linux dopuszcza czytanie pakietu, konfiguracji, środowiska i przygotowanych PDF-ów. Landlock blokuje połączenia TCP ekstraktora.

```sh
CHECK="$(mktemp -d)"
git clone --no-local . "$CHECK/czysta"
cd "$CHECK/czysta"
cc -std=c11 -O2 -Wall -Wextra -Werror evaluation/restrict_linux.c -o "$CHECK/restrict-linux"
python -m unittest discover -s evaluation -p 'test_*.py'
time python demo/rozszerzalnosc/accept.py --work "$CHECK/odbior" \
  --dataset "$UZP_DATA" --ocr-data "$OCR_DATA" --restrict-linux "$CHECK/restrict-linux"
git diff --name-only c01401cd7abdf82655b18188f68cb46652dc239e 72337e2164f871fa3b1d6c63edde0381b7ed8b31
```

Test generuje PDF-y, uruchamia publiczne CLI i porównuje zawartość obu zawiadomień, sygnały oraz numery stron i linie źródłowe z `expected.json`. W profilu domyślnym trzy syntetyki mają dać 0 bajtów. W profilu demo obcy syntetyk nadal ma dać 0 bajtów. Regresja porównuje ścieżki i SHA-256 rozwojowego `case_10` oraz siedmiu pozostałych negatywów z czystym A. Do wejścia trafiają tylko wskazane PDF-y. Test nie używa etykiet ani danych walidacji i testu końcowego. Próbę przed dodaniem klasy odtworzysz na rewizji `c01401cd7abdf82655b18188f68cb46652dc239e` z flagą `--before`. Plik klasy dochodzi w rewizji `72337e2164f871fa3b1d6c63edde0381b7ed8b31`.

## Ostatnie 50 sekund prezentacji

- **1:10–1:20** Pokaż `git diff --name-only c01401cd7abdf82655b18188f68cb46652dc239e 72337e2164f871fa3b1d6c63edde0381b7ed8b31`, skopiuj jeden plik poleceniem `cp` z próby jurora i uruchom CLI.
- **1:20–1:40** Pokaż oba JSON-y, 0 bajtów pisma obcego i termin na stronie 2.
- **1:40–2:00** Pokaż wynik odbioru z czystej kopii, 11/11 zgodnych ścieżek i sum SHA-256 oraz 8/8 pustych negatywów rozwojowych. Pliki dowodowe zachowuje katalog podany w `--work`.

Przed pokazem uruchom raz pełny odbiór i zostaw jego terminal otwarty przy podsumowaniu. Następny krok dla koordynatora to włączenie tej sekwencji do dwuminutowej próby na docelowym wydaniu.
