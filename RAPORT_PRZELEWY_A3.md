# Przelewy w A3. Pomiar na źródłach zewnętrznych

Porównanie odbyło się 21 listopada 2026 na VPS `hacknation`. Wersja początkowa to `5de75693429d9699368b958cd54eda4dd76e4900`, a wersja po poprawce to `1503772cbffe5369a4c9bc8548221a445fed7e8e`. Obie uruchomiono tym samym lokalnym CLI, z polskim OCR i bez LLM. Poprawka rozpoznaje bankowe nagłówki, czyta strony rachunku według etykiet, odróżnia status oczekujący od wykonanego oraz czyta kwotę i datę w tabelach. Ponawia odczyt niepewnego identyfikatora tylko przy zgodności dwóch kadrów i zachowaniu cyfr widocznych w pierwotnym odczycie.

## Wyniki

| Próba | Pierwotne A3, mikro-F1 | Po poprawce, mikro-F1 | TP / FP / FN po poprawce | Pełne pozytywy po poprawce |
|---|---:|---:|---:|---:|
| Rozwój, 2 polskie przelewy i 2 podobne dokumenty obce | 0,00%* | 91,67% | 11 / 1 / 1 | 1/2 |
| Rozwój, 40 przelewów UZP przekształconych w skany | 81,63% | 90,17% | 211 / 17 / 29 | 20/40, wcześniej 13/40 |
| Odłożone, 11 PDF-ów z tekstem z generatora KontoBank | 0,00%* | 98,11% | 52 / 0 / 2 | 9/11 |
| Odłożone, skany tych samych 11 operacji | 0,00%* | 98,11% | 52 / 0 / 2 | 9/11 |
| Odłożone, polska ilustracja Pekao24 po anonimizacji | 0,00% | 0,00% | 0 / 0 / 2 | 0/1 |
| Odłożone, 3 poradniki bankowe | 3/3 plików 0 B | 3/3 plików 0 B | 0 / 0 / 0 | – |
| Dotychczasowy development UZP, wszystkie trzy klasy i negatywy, 128 PDF-ów | 99,63% | 99,63% | 1355 / 5 / 5 | 128/128 identycznych plików wynikowych |

\* Liczba diagnostyczna z miernika. Pierwotne A3 utworzyło puste pliki dla prawdziwych przelewów, więc miernik oznaczył te przebiegi `valid_run=false`. Na polskim zbiorze rozwojowym pierwotne A3 dodatkowo zwróciło niepusty JSON dla KSeF. Po poprawce wszystkie przebiegi z tabeli mają `valid_run=true` i przechodzą kontrolę struktury. Dla samych negatywów mikro-F1 ma zerowy mianownik. Wynik pliku liczy się wówczas jako poprawny, gdy ma dokładnie 0 bajtów.

- **KontoBank.** W obu wersjach PDF odczytano 11/11 dat operacji, kwot, tytułów i rachunków nadawcy. Dla rachunku odbiorcy poprawnych było 8 z 10 wydrukowanych wartości. W dwóch dokumentach wynik zawierał `null`. W jedenastym rachunek odbiorcy był niepodany. Żaden z przykładów nie zawierał numeru referencyjnego. Zestaw obejmuje 6 przelewów przychodzących i 5 wychodzących z sześciu kont demonstracyjnych. Cztery tytuły powtarzają się w jednym dwujęzycznym szablonie. PDF i jego raster liczymy w osobnych wierszach. [Dokumentacja publicznego generatora Kontomatik](https://developer.kontomatik.com/first-steps/pdf-confirmations-parsing/#testing)
- **Dwa polskie potwierdzenia rozwojowe.** A3 poprawnie wyprowadza kwotę, datę, tytuł i oba rachunki na obu dokumentach. Odczytuje też identyfikator z przykładu Novum. Na obrazie eCorpoNet odczytało `UTT` w miejscu `1/7/7`. Wzór KSeF z nagłówkiem „Potwierdzenie transakcji” oraz ekran wyboru koszyka uzyskały pliki 0 B. Przykład Banku Kaszubskiego przedstawia ten sam układ Novum co ilustracja z Siedlca i nie powiększa próby. [Siedlec, s. 82](https://banksiedlec.pl/web/files/37822/Internet-Banking-klienta-indywidualnego-instrukcja-uzytkownika-wersja-28.40.pdf) · [Włoszczowa, s. 20](https://www.bs-wloszczowa.com.pl/aktualnosci/nowa-wersja-ecorponet/download/1.pdf) · [MF, KSeF](https://ksef.podatki.gov.pl/informacje-ogolne-ksef-20/potwierdzenie-transakcji/) · [Asseco, s. 49](https://www.bsklodzko.pl/images/pdf/pliki-do-pobrania/def3000_CBP_Miniaplikacja_Przelewy.pdf)
- **Polskie potwierdzenie odłożone.** Na ilustracji Pekao24 z materiału Politechniki Poznańskiej trwale zakryto piksele z danymi stron i numerem referencyjnym przed utworzeniem nowego PDF-u. Wzorzec zawiera wyłącznie czytelne `200,87 PLN` i `2021-03-12`. Obie wersje rozpoznały klasę. OCR zniekształcił zarówno napis „Kwota operacji”, jak i datę księgowania. Oba pola pozostały puste. [Politechnika Poznańska, s. 16](https://css.put.poznan.pl/sites/default/files/2025-03/PROCEDURY-27.10.2023.pdf)
- **Skanowanie starych danych rozwojowych.** Pełne odpowiedzi wzrosły z 13 do 20. Spośród 40 skanów poprawnych było 37 kwot, 36 dat, po 38 rachunków każdej strony, 37 identyfikatorów i 25 tytułów. Po zmianie wystąpiło 0 fałszywie podanych rachunków, a każde wcześniej poprawne pole zostało zachowane. Te 40 renderów mierzy wpływ utraty warstwy tekstowej na znane układy.

## Rozdzielenie danych i odbiór

Przed pierwszą zmianą kodu zapisano źródła, definicje pól, listy PDF-ów i etykiety. Przy anotowaniu widziałem przykładowy układ KontoBank. Wyniki ekstraktora na części odłożonej zostały odsłonięte dopiero po zamrożeniu commita. Rozwój i część odłożona mają zero wspólnych sum SHA-256 i zero wspólnych rodzin uwzględnionych w inwentarzu. Nowe PDF-y mają także zero kolizji z manifestami UZP development-40, validation-10, final-10 i z poprzednią próbą 10 pełnych spraw A3. Oryginał i jego raster mają różne hashe, ale ten sam identyfikator operacji w inwentarzu. Cały generator trafił do jednej części. Ogólny wynik konkursowy na pełnej sprawie pozostaje niewyznaczony dla nowego commita.

Referencje dla trzech polskich ilustracji przygotowano z obrazu. Dla fikcyjnych transakcji uzgodniono kwoty, kierunki i tytuły z danymi demonstratora, a datę operacji i podział ról z konkretnym PDF-em. Dla operacji obciążeniowej przyjęto bezwzględną kwotę przelewu. Data operacji ma pierwszeństwo przed datą księgowania. Pole numeru operacji zawiera wyłącznie identyfikator pokazany na dokumencie. Lokalne etykiety zewnętrzne opracowano na potrzeby tego pomiaru.

Prywatny przebieg na VPS używał Python 3.13, Landlock, odciętego TCP, neutralnych ścieżek i osobnych katalogów etykiet. Dostęp ekstraktora ograniczono do produktu, wejścia, OCR, katalogów wyjściowych i niezbędnych bibliotek. Miernik i próg zaliczenia zachowano. Python przeszedł 24 testy jednostkowe. Wszystkie 128 wyników pokryło się bajtowo z pierwotnym A3. Dwa dodatkowe przebiegi nazewnicze obejmowały 128 losowych i 128 mylących ścieżek, ze zgodną treścią oraz diagnostyką. Docker Compose w kontekście rootless na VPS odtworzył bajt w bajt wynik prywatnego CLI na czterech polskich dokumentach rozwojowych.

## Dane i powtórzenie odczytu wyniku

Na VPS katalog `~/uzp-parallel/a3-przelewy-dane/corpus-v1/` zawiera PDF-y, ręczne referencje, inwentarz rodzin i sześć manifestów. Jego `seal.json` ma SHA-256 `ff41aa86662a51e55a8db3a89f5af1f9da9766a227997019d9ae1d1ab8eae886`. W katalogu `measurements/` obok korpusu zapisano JSON-y wynikowe, diagnostykę, czas, podsumowania i pełne raporty miernika. Plik [indeksu źródeł i manifestów](evaluation/przelewy-zewnetrzne-v1.json) opisuje dokładne wersje. Archiwum robocze dla zespołu znajduje się w `~/uzp-parallel/a3-przelewy-dane/pakiet-testowy-przelewy-v1.tar.gz`.

Poniższe polecenia sprawdzają sumę manifestu i pozwalają ponownie policzyć wynik utrwalonych predykcji. Nie wykonują kolejnego przebiegu na odłożonym zbiorze.

```bash
cd ~/uzp-parallel/a3-przelewy
dane=~/uzp-parallel/a3-przelewy-dane
narzedzia=~/uzp-parallel/rc1-proof/acceptance.4PsV2H5A/tools
sha256sum "$dane/corpus-v1/seal.json"
"$narzedzia/venv/bin/python" -B evaluation/score.py "$dane/corpus-v1" \
  "$dane/measurements/blind-candidate/held_native/output" \
  --manifest "$dane/corpus-v1/manifests/held_native.json"
PYTHONPATH=. "$narzedzia/venv/bin/python" -B -m unittest discover -s evaluation -q
```

Dalszą pracę rozpoczyna powtórny odczyt kwoty i daty na polskich skanach rozwojowych o niskiej rozdzielczości. Warunkiem odbioru jest poprawna para kwota–data na nowych polskich układach oraz pusty plik dla powiązanej faktury, przy zachowaniu 128 starych wyników. Odłożono do tego nową parę KARR w `~/uzp-parallel/a3-przelewy-dane/reserve-karr`. Strona 3 zawiera przykładowe potwierdzenie w układzie mBank, strona 2 fakturę na tę samą kwotę. Zachowano oryginalną warstwę tekstową i osobny raster każdego dokumentu. Obie strony rachunku w tym przykładzie mają wydrukowane identyczne zera, dlatego rozróżnienie stron wymaga innego źródła. Przed kolejnym strojeniem warto dołożyć do rezerwy potwierdzenia z różnymi numerami i z przynajmniej dwóch innych polskich układów. Wyniki A3 na parze KARR pozostają nieodczytane. [KARR, s. 2–3](https://karrsa.eu/wp-content/uploads/2023/03/INSTRUKCJA-ROZLICZENIA-POZYCZKI-UNIWERSALNEJ.pdf)
