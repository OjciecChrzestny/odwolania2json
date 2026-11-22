# Pełny tekst PDF i rozpoznawanie przelewów przed zapisem 0 B

22 listopada 2026 r. na deweloperskim VPS porównaliśmy opublikowane A3 `ec654135812a8579829d7258e78eda5ab8438108` z kandydatem `6eb211c39c6c549dbeaf6ece5dfe52d3c234e12d`. Kandydat domyślnie czyta tekst wszystkich stron i ma budżet OCR do 6 różnych stron na PDF. Scaleway uruchamia się osobnym poleceniem.

## Siedem pominiętych przelewów i cztery podobne negatywy

Przelewy to siedem wcześniej pominiętych skanów z dziesięciu publicznych przelewów UZP. Negatywy to syntetyczna faktura, wyciąg z kilkoma operacjami, oczekująca dyspozycja i obciążenie kartowe. Wszystkie 11 dokumentów ma po jednej stronie. Kolejność, sumy SHA-256, referencje, zasady wyboru i limity wywołań zamroziliśmy przed pomiarem. Program przetwarzał PDF-y pod neutralnymi nazwami. Referencje były dostępne wyłącznie miernikowi. [Publiczna paczka UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/eadffbce531eeac876d0f7e62c1cc6e857b05796)

| Wariant | TP / FP / FN / TN klasy przelewu | F1 klasy | TP / FP / FN pól | Mikro-F1 pól | Czas 11 PDF | Wywołania | Koszt taryfowy API |
|---|---|---:|---|---:|---:|---:|---:|
| A3 przed zmianą | 0 / 0 / 7 / 4 | 0% | 0 / 0 / 37 | 0% | 16,44 s | 0 | 0 EUR |
| A3, pełny tekst | 0 / 0 / 7 / 4 | 0% | 0 / 0 / 37 | 0% | 17,39 s | 0 | 0 EUR |
| A3, pełny tekst i Scaleway | 2 / 0 / 5 / 4 | 44,44% | 3 / 3 / 34 | 13,95% | 103,76 s | 11 | 0,00441330 EUR |

Model otrzymywał render i maksymalnie 6000 znaków tekstu pierwszej strony. Kandydat trafiał do API po lokalnym rozpoznaniu jako obcy, jeżeli pierwsza strona zawierała sygnał finansowy albo był to jednostronicowy skan z udanym OCR. Model wskazywał klasę i dwa fragmenty dokumentu. Przy akceptacji co najmniej jeden fragment musiał wystąpić w lokalnym odczycie. Sześć pól wyznaczał dotychczasowy ekstraktor A3.

Model wskazał wykonany przelew dla 7/7 przelewów i dla obciążenia kartowego. Przy samym werdykcie modelu F1 klasy wyniosłoby 93,33% (7 TP, 1 FP, 0 FN, 3 TN). To obliczenie dotyczy wyłącznie klasy. Weryfikacja cytatów zatrzymała kartę oraz pięć prawidłowych przelewów. Wszystkie cztery negatywy dostały plik 0 B.

W dwóch utworzonych JSON-ach zgadzały się dwa rachunki odbiorcy i jeden tytuł. Oba rachunki nadawcy i drugi tytuł były błędne. Lokalny odczyt pozostawił puste daty oraz kwoty. Żaden z siedmiu przelewów nie miał kompletu prawidłowych wartości referencyjnych. Diagnostyka skierowała wszystkie jedenaście dokumentów do weryfikacji człowieka.

Wszystkie trzy procesy CLI zwróciły kod 0 i wytworzyły komplet 11 plików. Ścisły miernik oznaczył jednak `valid_run=false` we wszystkich trzech wariantach. Pusty plik dla oczekiwanego przelewu daje błąd parsowania i brakujące wartości. Takich plików było odpowiednio 7, 7 i 5. Mikro-F1 w tabeli opisuje te błędy na dobranej próbie. [Miernik](../../evaluation/score.py)

## Regresja na 128 PDF-ach

Zbiór rozwojowy zawiera po 40 odwołań, pełnomocnictw i przelewów oraz 8 negatywów. Obie próby mają łącznie 139 różnych hashy PDF. Poniższe wartości dotyczą aktualnych publicznych etykiet.

| Wariant | Mikro-F1 pól | TP / FP / FN pól | Czas 128 PDF | Wywołania | Koszt taryfowy API |
|---|---:|---|---:|---:|---:|
| A3 przed zmianą | 99,9265% | 1359 / 1 / 1 | 13,27 s | 0 | 0 EUR |
| A3, pełny tekst | 99,9265% | 1359 / 1 / 1 | 15,38 s | 0 | 0 EUR |
| A3, pełny tekst i Scaleway | 99,9265% | 1359 / 1 / 1 | 32,91 s | 2 | 0,00080445 EUR |

Wszystkie 128 wyników w każdym wariancie było identycznych bajt w bajt. W każdym przebiegu miernik i kontrola schematów potwierdziły ważność. Wszystkie 40 przelewów miało komplet poprawnych pól, 40 odwołań miało właściwe ID, a 8 negatywów miało po 0 B. Rozbieżność jednego pola dotyczy pełnomocnictwa. Na historycznej wersji etykiet te same pliki osiągają 99,6324% (1355 / 5 / 5).

W 20 dokumentach liczących ponad sześć stron dawny limit pomijał 111 stron. Kandydat odczytał tekst ze wszystkich 111. Najdłuższy dokument miał 31 stron. Syntetyczny PDF z numerem transakcji `0007` wyłącznie na stronie 7 dał poprawną wartość i wskazanie strony 7 w diagnostyce, bez OCR. Nieudana próba OCR również zużywa jednostkę budżetu. Reguły klasyfikacji nadal mają własne zakresy stron.

## Koszt, czas i odtworzenie

Użyliśmy modelu `mistral-small-3.2-24b-instruct-2506` przez Scaleway. Wszystkie 13 wywołań zakończyło się HTTP 200. Dostawca zwrócił 28 239 tokenów wejścia i 507 wyjścia dla próby 11 PDF-ów oraz 5167 i 84 dla zbioru 128. Koszt taryfowy wynosi łącznie **0,00521775 EUR** według stawek 0,15 EUR za milion tokenów wejścia i 0,35 EUR za milion tokenów wyjścia. Rachunek może uwzględniać dostępny pakiet bezpłatny. Czasy w tabelach to pojedyncze pomiary całej partii, łącznie z OCR, API i zapisem. Kontener miał limit czasu CPU odpowiadający dwóm rdzeniom, 16 GB pamięci i `OMP_THREAD_LIMIT=1`. [Cennik Scaleway](https://www.scaleway.com/en/generative-apis/)

Dla profilu lokalnego użyj polecenia z [RUN.md](../../RUN.md). Na VPS zbudowaliśmy z czystego drzewa obraz `odwolania2json-jury:6eb211c39c6c` i wykonaliśmy z niego całe polecenie jurora. Odtworzyło ono wynik ze strony 7 i wszystkie 128 plików. Przeszło też 181 testów automatycznych. Wariant z API można uruchomić z kopii źródeł z zainstalowanymi zależnościami OCR i skonfigurowanym dostępem Scaleway. Argument `--max-calls` ogranicza liczbę wywołań w partii.

```sh
python -m experiments.transfer_api.negative_verifier \
  --input wejscie --output wynik-api --diagnostics diagnostyka-api/przebieg.json \
  --ocr-data "$TESSDATA" --ocr-max-pages 6 --max-calls 11
```

Na VPS w katalogu `~/uzp-parallel/koordynacja/runda-96f88b6/tekst-ocr-scaleway-v1/` są protokół, manifesty, dowody HTTP i zużycia tokenów w diagnostyce, wyniki wszystkich wariantów i `ocena.py`. Polecenie poniżej ponawia wyłącznie punktację zapisanych wyjść i porównanie bajtowe.

```sh
"$HOME/uzp-parallel/rc1-proof/acceptance.4PsV2H5A/tools/venv/bin/python" -B \
  "$HOME/uzp-parallel/koordynacja/runda-96f88b6/tekst-ocr-scaleway-v1/ocena.py"
```

| Zawartość | SHA-256 |
|---|---|
| Protokół przed wywołaniami | `831c01ac592f1b62a5379817e03c42e84c6f5484e89506ab167ce49778f40ce6` |
| Manifest 7 + 4 | `6835e43d56293ce0516ae84f69573686586837d7212a4a129ca5eed2e7f04f05` |
| Manifest rozwojowy 128 | `40570c27716833081a6550d936c9b3a0cb0a1d133329c8b0e98a453ef66d0227` |

Pełny odczyt tekstu jest gotowy do użycia w A3. Scaleway pozostaje opcją eksperymentalną. Następną próbę warto zamrozić na innych szablonach i sprawdzić w niej odczyt wycinków kwoty, daty i rachunku nadawcy z potwierdzeniem ich położenia.
