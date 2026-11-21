# Dwuminutowy pokaz Odwołania2JSON

Otwórz `prezentacja.pdf`, terminal i dwa syntetyczne PDF-y z przygotowanej próby. W terminalu przygotuj polecenia z sekcji „Próba na żywo”. Trzy ekrany w `ekrany-rezerwowe.pdf` są zapisem wcześniejszego przebiegu. Przy awarii przełącz się na odpowiedni ekran i powiedz „To zapis próby na syntetycznych dokumentach”.

## 0:00–0:40 · PDF, CLI, JSON i negatyw

**Na ekranie.** Slajd 1, następnie `input/doc_01.pdf`. Uruchom etap `przelew`. Zatrzymaj widok na `domyslne/output/doc_01.json` i wierszu `doc_02.json: 0 B`.

**Tekst.** „To fikcyjne potwierdzenie przelewu zapisane jako doc zero jeden. Wkładam PDF do katalogu wejściowego i uruchamiam odwołania dwa JSON. Wynik zawiera sześć pól. Kwota to sto dwadzieścia trzy złote i czterdzieści pięć groszy, a rachunki mają osobne role. Drugie pismo ma datę i kwotę, ale jest wezwaniem do zapłaty. Jego plik wynikowy ma zero bajtów.”

## 0:40–1:10 · Źródło pola i jakość

**Na ekranie.** Slajd 2, wycinek źródłowy `Kwota: 123,45 PLN` i reguła `kwota_operacji`. Potem slajd 3. Nie pokazuj akt z odłożonych spraw.

**Tekst.** „Reguła kwota operacji wskazuje stronę pierwszą. A ma mikro F jeden zero przecinek dziewięć osiem siedem osiem na trzydziestu dwóch walidacyjnych PDF-ach. Jeden przelew uznał za obcy i przebieg jest nieważny. A dwa ma zero przecinek dziewięć dziewięć sześć trzy na stu dwudziestu ośmiu rozwojowych PDF-ach. Odzyskał dwa syntetyczne przelewy. Wynik jury jest nieznany.”

## 1:10–2:00 · Dodanie klasy i regresja

**Na ekranie.** Slajd 4, potem wynik `git diff --name-only`. Uruchom etap `klasa`, który kopiuje plik i przetwarza dwa zawiadomienia oraz pismo obce. Pokaż `2026-12-03` z drugiej strony, `doc_03.json: 0 B` oraz porównanie sum kontrolnych. Zakończ liczbą z regresji rozwojowej integratora.

**Tekst.** „Diff pokazuje jeden nowy plik. Kopiuję konfigurację zawiadomienia obok trzech klas konkursowych. Pierwszy dokument zwraca sygnaturę i termin. Trzeci grudnia dwa tysiące dwudziestego szóstego roku widnieje na stronie drugiej. W JSON-ie data ma format ISO. Obce pismo daje zero bajtów. Po dodaniu klasy wszystkie cztery syntetyczne wyniki pozostały identyczne, po jednym z każdej klasy i jeden obcy. W odbiorze rozwojowym kandydata zgadzało się jedenaście wyników, w tym osiem pustych negatywów.”

## Próba na żywo

Użyj osobnej czystej kopii zatwierdzonego kodu `KOD` i nowego katalogu `WORK`. Zainstaluj narzędzia pokazu w osobnym środowisku przez `python -m pip install -r requirements-pokaz.txt`. Do powtórzenia bez sieci po instalacji użyj wcześniej zbudowanego obrazu z etykietą rewizji. Budowę oraz użyte ścieżki podaje `RAPORT-PROBY.md`.

```sh
# POKAZ wskazuje pliki delivery/final z gałęzi dokumentacyjnej.
python "$POKAZ/proba.py" "$KOD" "$WORK" przygotuj --sha "$RC_SHA" --image "$IMAGE"
python "$POKAZ/proba.py" "$KOD" "$WORK" przelew --sha "$RC_SHA" --image "$IMAGE"
git -C "$KOD" diff --name-only c01401cd7abdf82655b18188f68cb46652dc239e 72337e2164f871fa3b1d6c63edde0381b7ed8b31
python "$POKAZ/proba.py" "$KOD" "$WORK" klasa --sha "$RC_SHA" --image "$IMAGE"
```

Etapy wywołują publiczne CLI. Pierwszy przebieg jest równoważny poleceniu `python -m odwolania2json --input "$WORK/input" --output "$WORK/domyslne/output" --diagnostics "$WORK/domyslne/diagnostics/last-run.json"`. Ostatni etap dodaje `--config` i wywołuje narzędzie źródłowe `demo/rozszerzalnosc/pokaz.py zrodlo`. Gdy pokaz prowadzisz natywnie, pomiń `--image`. Do jednego przebiegu odbioru użyj `calosc` zamiast trzech etapów.

## Materiał rezerwowy i edycja slajdów

- Ekran 1 pokazuje przelew z rzeczywistej próby syntetycznej, pełny wynik i rozmiar wyniku pisma obcego.
- Ekran 2 pokazuje pole kwoty, stronę źródłową i regułę z diagnostyki.
- Ekran 3 pokazuje dodany plik, stronę 2, JSON, negatyw i regresję syntetyczną.

Edytuj treści i układ w `buduj.py`. Po przebiegu `calosc` uruchom `python "$POKAZ/buduj.py" "$WORK" "$MATERIALY"`. Budowa używa fontów systemowych Lato i DejaVu Sans Mono dostępnych na VPS. Zapisz oba PDF-y lokalnie przed pokazem.

Następny krok z osobą prezentującą to zmierzenie przejścia od terminala do drugiej strony PDF-u w ostatnim segmencie, z projektorem i bez połączenia z VPS. Podstawę oszacowania narracji podaje raport próby.
