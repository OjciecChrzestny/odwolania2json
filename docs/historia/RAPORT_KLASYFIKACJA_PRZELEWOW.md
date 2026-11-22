# Rozpoznawanie wykonanych przelewów na publicznych skanach

Na drugiej rezerwie A3 z rewizji `4edfd0cbfa4bc4a4bb3c3e1b8a8ab0c5a554abcf` poprawnie rozpoznało 3/3 wykonane przelewy i pozostawiło 2/2 formularze jako pliki 0 B. Wszystkie trzy JSON-y przeszły walidację schematu. Ścisłe mikro-F1 sześciu pól wyniosło **41,38%**. Żaden przelew nie miał sześciu poprawnych pól. Regresja 128 PDF-ów UZP przeszła bajtowo. Wszystkie przebiegi wykonano na VPS przez Docker Compose z wyłączoną siecią dla ekstraktora.

## Dwie próby kontrolne

Punktem odniesienia było A3 `a42b78d`. Manifest każdej próby utrwalono przed zmianą reguł ocenianą na tej próbie. W wejściu ekstraktora były wyłącznie PDF-y. Etykiety, rodziny układów, źródłowe nazwy plików i nazwy banków służyły przygotowaniu próby oraz ocenie. Klasyfikator opiera się na treści strony. Pierwsza poprawka wymaga dowodów wykonania operacji i wypełnienia pól na tej samej stronie. Druga łączy nagłówki tabeli z wartościami w sąsiednim wierszu. Testy obejmują również płatność kartą, oczekującą dyspozycję i dowody rozrzucone po różnych stronach.

| Pomiar | Wersja A3 | Przelewy z poprawną klasą | Negatywy 0 B | F1 klasy przelew | Mikro-F1 pól | `valid_run` |
|---|---|---:|---:|---:|---:|---|
| Pierwsza rezerwa, pierwsze otwarcie | `a42b78d` oraz `ca0c719` | 2/3 | 2/2 | 80,00% | 58,33% | nie |
| Druga rezerwa, pierwsze otwarcie | `a42b78d` oraz `ca0c719` | 2/3 | 2/2 | 80,00% | 24,00% | nie |
| Druga rezerwa, to samo porównanie | `4edfd0c` | 3/3 | 2/2 | 100,00% | **41,38%** | tak |
| Pierwsza rezerwa, późniejsza regresja | `4edfd0c` | 3/3 | 2/2 | 100,00% | 66,67% | tak |

W pierwszej próbie oba warianty wydały plik 0 B dla wykonanego przelewu DNB. W drugiej próbie ten sam błąd dotyczył Banku Zachodniego WBK w dwóch wcześniejszych wersjach. Miernik potrafi w takim przypadku policzyć diagnostyczne mikro-F1, ale zgłasza nieważny przebieg, ponieważ spodziewa się JSON-u dla każdego przelewu. Kontrola drzewa i schematów drugiej rezerwy dla `4edfd0c` dała `valid_contract=true` i 5/5 dokumentów. Dobór drugiej poprawki oparto na osobnym materiale rozwojowym. Późniejsze rozpoznanie DNB stanowi regresję na otwartym już materiale.

Na pierwszej próbie rozwojowej liczba rozpoznanych przelewów wzrosła z 1/3 do 3/3. Oba druki miały po 0 B, a mikro-F1 pól wzrosło z diagnostycznych 34,78% do ważnych 44,44%. Na drugim zbiorze rozwojowym liczba rozpoznanych przelewów wzrosła z 1/2 do 2/2, z jednym poprawnym negatywem. Ten zbiór miał wyłącznie etykiety klas. Jedno z potwierdzeń opublikowano z obciętą prawą krawędzią.

## Skąd pochodzi 41,38%

Na trzech przelewach z drugiej rezerwy wzorzec obejmował 18 wartości. Miernik naliczył 6 TP, 5 FP i 12 FN. Przy błędnej, niepustej wartości jedno pole zwiększa zarówno FP, jak i FN.

| Pole | TP | FP | FN |
|---|---:|---:|---:|
| `data_operacji` | 2 | 0 | 1 |
| `kwota` | 2 | 0 | 1 |
| `tytul` | 0 | 3 | 3 |
| `numer_transakcji` | 2 | 1 | 1 |
| `z_rachunku` | 0 | 1 | 3 |
| `na_rachunek` | 0 | 0 | 3 |

Raiffeisen i BZ WBK miały poprawną datę i kwotę. W Deutsche Bank poprawny był jedynie numer transakcji. Wszystkie trzy tytuły były błędne. Spośród sześciu oczekiwanych rachunków program podał jeden, również błędny.

## Dobór i regresje

Pierwszy podział zawierał pięć dokumentów rozwojowych i pięć kontrolnych, drugi odpowiednio trzy i pięć. Na każdy dokument przypadał jeden wariant słabego skanu. Formularze wielostronicowe liczono po jednym razie. Są to pojedyncze dokumenty, więc te pomiary nie oceniają dziesięciu pełnych spraw odwoławczych.

- Pierwsze zamrożenie utrwalono w `ab088d7` o 21:36:55 UTC 21 listopada 2026. Rezerwa zawierała DNB, mBank CompanyNet, Credit Agricole CA24, dyspozycję dewizową oraz zgodę na obciążanie rachunku. Dwa podobne druki WP przydzielono do części rozwojowej. [Źródła, układy i sumy kontrolne](../../evaluation/przelewy-klasyfikacja-v4.json)
- Drugie zamrożenie utrwalono w `934033e` o 21:49:38 UTC tego samego dnia. Rezerwa zawierała Raiffeisen R-Online Biznes, BZ WBK, Deutsche Bank db powerNET oraz dwa bankowe formularze reklamacji. PekaoBIZNES24 i druki WP powtarzały się w materiałach rozwojowych. [Źródła, układy i sumy kontrolne](../../evaluation/przelewy-klasyfikacja-v4b.json)
- W każdym podziale część rozwojowa i kontrolna miały zero wspólnych SHA-256, odcisków pierwszej strony, publikacji i rodzin układów. Porównanie z wcześniejszymi plikami także dało zero identycznych SHA-256. Sprawdzono odpowiednio 145 i 165 wcześniejszych odcisków stron. Wszystkie sześć odłożonych przelewów dotyczyło wpłat na rzecz UZP, a dwa w drugiej rezerwie pochodziły od tej samej organizacji, w różnych latach i bankach.
- Wszystkie 128 wyników UZP jest bajtowo zgodnych z bazą. Próba obejmowała 40 odwołań, 40 pełnomocnictw, 40 przelewów i 8 negatywów. Mikro-F1 pól wyniosło 99,63% (1355 TP, 5 FP, 5 FN). Wszystkie 40 ID zarzutu pozostały poprawne.
- Na wcześniejszej rezerwie v3 wszystkie 8 wyników pozostało identycznych z bazą. A3 wciąż odrzuca publiczne potwierdzenie Alior z BIP. Rozpoznano tam 5/6 przelewów oraz 2/2 negatywy, a `valid_run` pozostał fałszywy.
- Mylące nazwy plików we wszystkich 18 dokumentach obu podziałów dały identyczne wyniki i diagnostykę po uzgodnieniu ścieżek. Wersja `4edfd0c` przeszła 39 testów projektu oraz 7 lokalnych testów eksperymentu API. Liczba wywołań modelu w pomiarze wyniosła zero.

## Sprawdzenie zapisanego pomiaru na VPS

Na koncie `dev-viralpay` poniższe polecenia sprawdzają zapisane wyniki. Pomiaru jednokrotnego nie trzeba powtarzać.

```sh
cd ~/uzp-parallel/a3-klasyfikacja
p=~/uzp-parallel/a3-przelewy-dane/przelewy-klasyfikacja-v4b
py=~/uzp-parallel/rc1-proof/acceptance.4PsV2H5A/tools/venv/bin/python
"$py" -B -m evaluation.score "$p/corpus" "$p/runs/candidate-hold/output" --manifest "$p/corpus/manifests/hold.json"
"$py" -B -m evaluation.check_outputs "$p/runs/candidate-hold/output" --manifest "$p/corpus/manifests/hold.json" --diagnostics "$p/runs/candidate-hold/diagnostics/last-run.json"
diff -qr ~/uzp-parallel/a3-przelewy-dane/karr-v2/measurements/regression-128-release/neutral/output "$p/runs/reg128/output"
```

Oczekiwane wyniki to `valid_run=true`, `valid_contract=true` dla pięciu dokumentów i kod wyjścia 0 dla porównania 128 plików. Zbiorczy zapis znajduje się w `$p/verification.json`. Obraz kandydata ma identyfikator `sha256:bfc78ed8ef249684fd86f8aeb78b6272ca8ab5cb7f6f7be065f16b910c0e9eb3`.

## Następny krok

Odzyskać i przypisać do stron numery rachunków na osobnych skanach rozwojowych. Przed strojeniem odłożyć nowe potwierdzenia z różnymi rachunkami odbiorców, również spoza UZP. Na tych samych wejściach porównać obie wersje pod względem poprawnych numerów po właściwej stronie, liczby zamian stron i błędnie dopisanych rachunków. Warunkiem przyjęcia zmiany jest wzrost liczby poprawnych rachunków względem `4edfd0c` w nowej próbie, zero zamian stron, brak wzrostu FP tych pól i zachowanie 128/128 wyników regresji.
