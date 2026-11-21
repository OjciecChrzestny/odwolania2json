# Rachunki nadawcy i odbiorcy na sześciu publicznych przelewach

Na VPS poprawione A3 odczytało **9 z 12 rachunków** w odpowiednich rolach (wcześniej 3/12). Mikro-F1 pól `z_rachunku` i `na_rachunek` wzrosło z **40,00% do 85,71%**. Żaden podany numer nie był błędny ani przypisany przeciwnej stronie. Obie wersje pominęły wykonany przelew Santander. Miernik wszystkich sześciu pól oznaczył oba przebiegi jako nieważne. Wszystkie 128 wcześniejszych wyników UZP pozostało identycznych bajtowo.

## Co i kiedy zamrożono

Wzorzec powstał przed poprawką przez odczyt obrazów stron. Obejmuje sześć różnych rachunków odbiorców i sześć odrębnych publikacji. Pięć wpłat trafiło poza UZP. Jedna to przelew przychodzący między przedsiębiorstwami. Sześć potwierdzeń obejmuje pięć rodzin układów, ponieważ dwa dokumenty mBanku mają wspólne kolumny „Winien” i „Ma”. Są to potwierdzenia pojedynczych transakcji. Próba nie mierzy jakości na sześciu pełnych sprawach odwoławczych.

Manifest `4f474c6` z 21 listopada 2026 r., godz. 23:08:08 w Warszawie, poprzedza zmianę kodu. SHA-256 pieczęci wynosi `2d52bee3bfcd41cb6ee0a83106200dfd5f1cbbee6edfc3ffc409c7f5c7cfa3af`. Rozwojowe skany ING i DNB pochodzą z innych publikacji i rodzin układów niż sześć odłożonych dokumentów. W obu grupach i względem historycznych zbiorów porównanych w manifeście było zero wspólnych SHA-256. Porównanie z 181 wcześniejszymi odciskami pierwszych stron również dało zero identycznych odcisków. Wcześniejsze eksperymenty obejmowały już m.in. pokrewne formularze mBanku, Millennium, Pekao i CA24. [Manifest, źródła i strony załączników](evaluation/przelewy-rachunki-v5.json)

Z każdej strony wykonano jeden skan w skali szarości (96 dpi, rozmycie 0,55 px i JPEG o jakości 55). Pliki przekazano pod neutralnymi nazwami. W ekstraktorze działał lokalny OCR i reguły. Obrazy bazowy i kandydata uruchomiono na tych samych wejściach w Docker Compose z wyłączoną siecią. Wzorce pozostały poza montowaniami kontenera. Liczba wywołań LLM wyniosła 0.

## Wynik pierwszego porównania na odłożonych plikach

| Miara | Przed, `4edfd0c` | Po, `25fc429` |
|---|---:|---:|
| Rachunek nadawcy, poprawne / oczekiwane | 1/6 | 4/6 |
| Rachunek odbiorcy, poprawne / oczekiwane | 2/6 | 5/6 |
| Oba rachunki poprawne w jednym dokumencie | 1/6 | 4/6 |
| Mikro-F1 obu pól | 40,00% (3 TP, 0 FP, 9 FN) | 85,71% (9 TP, 0 FP, 3 FN) |
| Pełne zamiany stron / pola z numerem drugiej strony | 0 / 0 | 0 / 0 |
| Błędne inne numery / brakujące rachunki | 0 / 9 | 0 / 3 |
| Rozpoznane przelewy / w pełni poprawne JSON-y | 5/6 / 0/6 | 5/6 / 0/6 |
| Wszystkie sześć pól, wynik diagnostyczny | 54,55% (15 TP, 5 FP, 20 FN) | 68,85% (21 TP, 5 FP, 14 FN) |
| Czas sześciu PDF-ów na VPS | 12,04 s | 17,03 s |

Wynik rachunków uwzględnia brakujące pola także wtedy, gdy klasyfikator wydał plik 0 B. Dwie wartości odwrotne względem wzorca stanowią jedną pełną zamianę. Osobno mierzymy każdą wartość wpisaną w niewłaściwe pole, nawet gdy drugie pole jest puste lub poprawne. Każdy numer wzorcowy miał 26 cyfr, w tym początkowe zera, i był różny od numeru drugiej strony tej samej transakcji. [Kod miernika rachunków](evaluation/score_accounts.py)

| Odbiorca / układ | Poprawne rachunki przed | Poprawne rachunki po |
|---|---|---|
| Urząd Miejski w Gdańsku, mBank | 0/2 | 2/2 |
| Przedsiębiorstwo usługowe, mBank, przelew przychodzący | 0/2 | 2/2 |
| Sąd Rejonowy w Olsztynie, Millennium | tylko odbiorca | 2/2 |
| UZP, PekaoBiznes24 | 0/2 | tylko odbiorca |
| Urząd Miasta Torunia, Santander | 0/2, plik 0 B | 0/2, plik 0 B |
| Urząd m.st. Warszawy, CA24 | 2/2 | 2/2 |

Na całej próbie `evaluation.score` zwraca `valid_run=false` i kod 1, ponieważ Santander dostał 0 B. Kontrola drzewa i schematów według klas przypisanych przez CLI daje `valid_contract=true`. Dodatkowe przeliczenie wykonane po otwarciu próby, ograniczone do tych samych pięciu rozpoznanych dokumentów, daje 60,00% przed i 75,00% po zmianie, w obu przypadkach `valid_run=true`. Na tych pięciu dokumentach pozostały błędy m.in. tytułu i identyfikatora transakcji. Przeliczenie wyklucza błąd klasyfikacji z mianownika. Dla całej próby obowiązuje wiersz diagnostyczny w tabeli.

## Wdrożenie i regresja

Reguły wiążą rachunek z etykietą i stroną dokumentu. W tabeli dwukolumnowej używają położenia nagłówków i cyfr. Przy etykiecie „właściciel” korzystają z kierunku zaksięgowanej operacji. Nowy odczyt sprawdza długość i sumę kontrolną polskiego NRB. Gdy OCR widzi prawie cały numer, może ponownie odczytać ograniczony wycinek. Korekta wymaga zgodności dwóch odczytów i poprawnej sumy kontrolnej. Reguła dla potwierdzeń „Winien / Ma” wymaga nagłówka potwierdzenia i danych transakcji na tej samej stronie. Na dwóch dokumentach rozwojowych liczba poprawnych rachunków wzrosła z 0/4 do 3/4, bez zamian. Jeden uszkodzony odczyt pozostał pusty.

- 128/128 wyników kandydata jest identycznych bajtowo z dotychczasowym A3. Próba zawierała po 40 odwołań, pełnomocnictw i przelewów oraz 8 negatywów z wynikiem 0 B. Mikro-F1 wyniosło 99,63% (1355 TP, 5 FP, 5 FN), przy `valid_run=true` i `valid_contract=true`.
- Zmiana nazw wszystkich sześciu PDF-ów na mylące nazwy dała identyczne pliki oraz diagnostykę po uzgodnieniu ścieżek. To kontrola zależności od nazwy, a liczebność rezerwy nadal wynosi sześć.
- Przeszło 46 testów projektu i 7 testów pilota wykonywanych bez połączenia z API. Sprawdzono m.in. odwrócone kolumny, rachunek przy przelewie przychodzącym, zera wiodące w próbie, zamianę tylko jednej strony, nieczytelne cyfry i sprzeczne odczyty. Na zapowiedzianym kryterium przyjęcia poprawki rachunków liczba TP wzrosła, liczba FP nie wzrosła, nie było zamian i przeszła regresja 128/128.

## Weryfikacja zapisanych wyników na VPS

Kod kandydata ma rewizję `25fc4294f7c5203e4e34300d4eefe6de3a3a1dba`, a baza `4edfd0cbfa4bc4a4bb3c3e1b8a8ab0c5a554abcf`. Weryfikacja obrazu objęła 13 plików produktu. Numery obrazów, sumy PDF-ów i moment otwarcia próby zapisano odpowiednio w `candidate.json` oraz `held-once.json` w katalogu pomiaru na VPS.

```sh
cd ~/uzp-parallel/a3-klasyfikacja
p=~/uzp-parallel/a3-przelewy-dane/a3-rachunki-v5
py=~/uzp-parallel/rc1-proof/acceptance.4PsV2H5A/tools/venv/bin/python
for version in base candidate
do
  "$py" -B -m evaluation.score_accounts "$p/corpus" "$p/runs/$version-hold/output" --manifest "$p/corpus/manifests/hold.json"
  "$py" -B -m evaluation.score "$p/corpus" "$p/runs/$version-hold/output" --manifest "$p/corpus/manifests/hold.json"
done
diff -qr ~/uzp-parallel/a3-przelewy-dane/przelewy-klasyfikacja-v4b/runs/reg128/output "$p/runs/reg128/output"
```

Pierwszy miernik wypisuje TP, FP, FN, mikro-F1 i obie miary zamian. Drugi wypisuje błąd dla przelewu z plikiem 0 B. Ostatnie polecenie ma zakończyć się kodem 0. Zbiorcze wyniki zawiera `$p/verification.json`.

**Następny krok.** Wdrożyć zaplanowaną w CLI listę dokumentów wymagających akceptacji. Santander i brak rachunku nadawcy w Pekao mogą odtąd służyć jako regresje. Pomiar ryzyka błędnej automatycznej akceptacji wymaga kolejnej, odłożonej próby z niezależnymi etykietami poprawności i czytelności.
