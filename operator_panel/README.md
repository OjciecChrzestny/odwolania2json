# Lokalny panel kontroli

Panel przetwarza własny PDF w trybie pokazowym i pozwala także otwierać istniejące wyniki. Lewa kolumna pokazuje dokumenty i powody kontroli. Po wyborze dokumentu można przejść na wskazaną fizyczną stronę PDF-u, rozwinąć tekst strony, sprawdzić pole z dowodem i zapisać decyzję.

## Własny PDF w przeglądarce

Z katalogu repozytorium, w aktywnym środowisku Pythona z zależnościami panelu:

```sh
python -m pip install -r operator_panel/requirements.txt
RUN=$(mktemp -d)
python -m operator_panel --demo-workspace "$RUN/przebiegi" --port 8765
```

Z polskim OCR zainstaluj dodatkowo `requirements-ocr.txt` i podaj katalog zawierający `pol.traineddata`:

```sh
python -m pip install -r requirements-ocr.txt
python -m operator_panel --demo-workspace "$RUN/przebiegi" --ocr-data "$TESSDATA" --port 8765
```

Połącz się przez tunel opisany niżej. W panelu wybierz **Wgraj własny PDF**, a potem **Przetwórz PDF**. Po zakończeniu panel otwiera surowy wynik, stronę i kontrolę. Zobaczysz 0 B dla dokumentu spoza klas albo komunikat odczytu, gdy PDF jest uszkodzony.

Tryb demo uruchamia lokalnie zwykłe `python -m odwolania2json` dla jednego PDF-u do 32 MiB. Każde uruchomienie zapisuje plik jako `dokument.pdf` w nowym przebiegu z własnymi katalogami `input/`, `output/` i `diagnostics/`. Identyfikator przebiegu jest w adresie panelu. Zachowaj adres i katalog, aby wrócić do wyniku i decyzji po restarcie. Przebiegi pozostają na dysku, dopóki operator ich nie usunie. Wskaż nowy katalog lub wcześniej utworzony przez panel. `--demo-workspace` ma własne ścieżki i można go uruchomić niezależnie od trybu istniejących raportów.

## Przegląd istniejących raportów na VPS

Z katalogu repozytorium. Użyj Pythona 3.13 i przygotuj osobny katalog przebiegu.

```sh
python3.13 -m venv "$HOME/.venvs/odwolania-panel"
. "$HOME/.venvs/odwolania-panel/bin/activate"
python -m pip install -r operator_panel/requirements.txt

RUN="$HOME/odwolania-panel-run"
IN="$RUN/input"
OUT="$RUN/output"
DIAG="$RUN/diagnostics/last-run.json"
mkdir -p "$IN"
# Włóż własne PDF-y do "$IN" lub jego podkatalogów.
python -m odwolania2json --input "$IN" --output "$OUT" --diagnostics "$DIAG"
python -m operator_panel --input "$IN" --output "$OUT" --diagnostics "$DIAG" --port 8765
```

Jeżeli ekstrakcja kończy się kodem 1, panel nadal pokazuje poprawnie odczytane dokumenty i informację o błędach pozostałych. Dla niestandardowych klas przekaż ten sam katalog `--config` obu poleceniom. Gdy istnieje już diagnostyka, wystarczy drugie polecenie z właściwymi ścieżkami.

Panel nasłuchuje na `127.0.0.1`. Do dostępu z laptopa uruchom w osobnym terminalu tunel SSH i wejdź na adres `http://127.0.0.1:8765`.

```sh
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8765:127.0.0.1:8765 hacknation
```

## Kontrola dokumentu

1. Wybierz dokument, a następnie pole w sekcji **Dowód i decyzja**. **Otwórz stronę dowodu** przechodzi na przypisaną stronę. Zmiana numeru strony pokazuje jej czytelność i fizyczny podgląd.
2. Pojedynczy cytat pochodzi z diagnostyki i może pochodzić z OCR. **Tekst strony** to dostępna natywna warstwa tekstowa PDF-u. Dowód o precyzji strony wskazuje miejsce, w którym operator może samodzielnie odszukać pole.
3. Użyj **Akceptuj wynik** albo **Skoryguj wybrane pole**. Pole tekstowe przyjmuje wartość bez cudzysłowów, a pole liczbowe akceptuje separator dziesiętny w postaci kropki lub przecinka. Jeśli schemat dopuszcza null, dostępne jest pole wyboru **Ustaw null**.
4. Wynik i jego SHA-256 pozostają bez zmian. Po zapisaniu decyzji panel pokazuje wpis z czasem i identyfikatorami, a przy korekcie także poprzednią i nową wartość. Możesz ponownie otworzyć rozpatrzony dokument po restarcie panelu. Dziennik znajduje się w pliku `last-run.decisions.sqlite3` obok raportu. Podmiana PDF-u lub wyniku blokuje zapis dla poprzedniej wersji. Po wykonaniu nowej ekstrakcji wybierz **Odśwież**.

Podgląd renderuje stronę do PNG i pokazuje zawartość dowodów jako tekst. Ścieżki plików pochodzą z istniejącego raportu, a dane wejściowe i surowe wyniki są otwierane do odczytu. Panel używa ewidencji blokady obok drzewa wyników oraz dziennika decyzji obok raportu.

## Rezerwowy przebieg w CLI

Zachowaj te same wartości `IN`, `OUT` i `DIAG`. Po `show` otwórz wskazaną stronę w lokalnym czytniku i skopiuj bieżący `review_id` do `ID`. Dla danego wyniku wybierz jedną akcję.

```sh
kontrola() {
  python -m odwolania2json --input "$IN" --output "$OUT" --diagnostics "$DIAG" review "$@"
}
kontrola list
kontrola show sprawa/przelew.pdf
kontrola accept sprawa/przelew.pdf --expect "$ID"
# Przykład alternatywnej akcji dla wyniku oczekującego na decyzję
kontrola correct sprawa/przelew.pdf --expect "$ID" --field przelew_bankowy.kwota --value 12.50
kontrola show sprawa/przelew.pdf
```

## Próba w Chromium

Próba tworzy wyłącznie fikcyjne PDF-y i uruchamia publiczne CLI oraz panel. W jednym przebiegu sprawdza klawiaturę, fizyczną stronę 2, cytat i jego brak, widok telefonu, bezpieczny tekst, błędny PDF, pustą kolejkę, wznowienie i podmianę pliku.

```sh
python -m pip install playwright
python -m playwright install chromium --only-shell
trial=$(mktemp -d)
python -B -m operator_panel.acceptance "$trial/run"
```

Skrypt zapisuje zrzuty widoku 1440×900 i 375×812 oraz raport `result.json`. Dla istniejącego raportu oczekuj 3 zgodnych SHA-256, negatywu 0 B, 2 decyzji po restarcie i HTTP 409 przy zapisie starej decyzji. W trybie demo Chromium wgrywa nowy przelew, negatyw i uszkodzony PDF oraz sprawdza także zachowanie surowego wyniku po decyzji. Aby dodać próbę rzeczywistego polskiego OCR, przekaż `--ocr-data "$TESSDATA"` do polecenia odbioru.
