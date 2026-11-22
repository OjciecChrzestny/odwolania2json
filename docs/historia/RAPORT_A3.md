# A3 — zamrożenie i odbiór rozwojowy

## Zamrożony zbiór

Przed pierwszą zmianą produktu na VPS zamrożono 10 publicznych spraw z [wydania danych UZP 84cc976](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/84cc976f0a9af5cee14f131c795f929134ca0fda/dane/skany). Każda zawiera odwołanie, pełnomocnictwo, potwierdzenie przelewu i trzy referencyjne JSON-y. W zbiorze są wyłącznie dokumenty trzech klas. Dla każdej trójki identyfikator mocodawcy łączy ją jednoznacznie z odwołującym, a numer postępowania w tytule przelewu wskazuje tylko jej odwołanie. Sprawdzenie z innymi numerami dało zero powiązań. Względem dotychczasowych 191 PDF-ów z 60 spraw i przykładów negatywnych stwierdzono zero wspólnych skrótów PDF, zero wspólnych etykiet według skrótu pliku i po kanonicznym zapisie JSON.

Audyt rodzin porównał pierwsze strony każdego z 30 nowych dokumentów z 60 starszymi dokumentami jego klasy, po usunięciu danych zmiennych i lokalnym OCR skanów. Porównano trójki kolejnych słów, pięcioznakowe fragmenty tekstu i rozkład zadruku. Maksymalna zgodność trójek słów między nowymi a starymi wyniosła 0,410 dla odwołań, 0,215 dla pełnomocnictw i 0,068 dla przelewów. W każdej klasie była niższa od najniższego podobieństwa starego dokumentu do jego najbliższego starego odpowiednika (0,431 / 0,457 / 0,112). Kontrola na dziewięciu dokumentach rozwojowych porównała odczyt cyfrowy z OCR tej samej strony. To empiryczny test odrębności od starych szablonów. Organizator nie publikuje identyfikatorów rodzin.

| Dowód | Wartość |
| --- | --- |
| Czas pieczętowania UTC | 2026-11-21 16:26:16 |
| Katalog na VPS | `~/uzp-parallel/a3-data/holdout-10-84cc976` |
| Manifest SHA-256 | `a87ed39171b9191f32a089b9e6490f4e2e3cc2c954b8feecd97c836a0bbc5dbf` |
| Potwierdzenie zamrożenia SHA-256 | `8a6dbf6ab72c1dfc3cf020e9f58a051bbd1722e0286fac6cd18ddff0d4c02fd7` |
| SHA-256 pliku SHA256SUMS | `eb866931d51e6f2c180285a269c086603ee105b4733b4ff5762f365aaebfe840` |
| Audyt na VPS | `~/uzp-parallel/a3-data/audit-84cc976/{confirm.py,freeze-verified.py,template-audit.json}` |
| Wersja bazowa | `373fafe5a9ff05638025636b323a3c7479a960d6`, drzewo produktu A2 `a359032b4478d458090e68b1b3c85084138eac98` |

Katalog i pliki zapieczętowano w trybie tylko do odczytu. Manifest ma neutralne nazwy wejść. Prywatne referencje, tabela źródeł i audyt znajdują się poza kopią produktu. Polecenie weryfikujące integralność na VPS to `(cd ~/uzp-parallel/a3-data/holdout-10-84cc976 && sha256sum --quiet -c SHA256SUMS)`. Ten etap nie uruchamia ekstraktora na nowym zbiorze.

## Wykonanie A3

Sprawdzony commit produktu to `e98988f8f0d707e4c72fdcc99910999084a6442b` (drzewo pakietu `f6f5e747389147375c6c8b7e2683293ef6f80d6e`). Poprzedza go osobny commit metryki zamrożenia `e2b4882`. Kod dostaje tekst i położenie stron. Ścieżka PDF służy czytnikowi do otwarcia pliku i CLI do odtworzenia nazwy oraz podkatalogu wyniku.

- Pełnomocnictwo obsługuje nagłówek „do reprezentacji” i zwrot „umocowuję”. Po rozpoznaniu pisma przewodniego reguła sprawdza strony 2–3, jeśli otwarcie dokumentu nie rozstrzyga klasy. Na dalszej stronie wymaga nagłówka i oświadczenia o umocowaniu. Ekstrakcja ról rozpoczyna się na stronie z dowodem. Opcjonalny polski OCR obejmuje brakującą warstwę tekstową w tym zakresie. Osobne próby chronią wezwania, instrukcje i wykazy załączników.
- Odwołanie rozpoznaje pierwszy zarzut numerowany cyfrą, rzymskim I albo słownie. Wyszukuje nagłówek w obrębie odczytanych stron, również po długim wstępie. Odcina następny zarzut i uzasadnienie. W obrębie pierwszego zarzutu priorytet ma zdanie wyraźnie wskazujące przedmiot zaskarżenia. Jawne wyłączenie czynności usuwa ją z wyboru oraz z przypisania daty. Odróżnia dokonanie od zaniechania oraz rozpoznaje parafrazę „pozbawienie wykonawcy prawa dalszego udziału w postępowaniu”. Opis nadal wynika z lokalnego słownika ID.

## Wyniki na VPS

| Sprawdzenie | A2 | A3 |
| --- | ---: | ---: |
| Ścisłe mikro-F1 na 40 sprawach rozwojowych | 0,9963235294 | 0,9963235294 |
| TP / FP / FN | 1355 / 5 / 5 | 1355 / 5 / 5 |
| Poprawna klasa pełnomocnictwa / odwołania / przelewu | 40 / 40 / 40 | 40 / 40 / 40 |
| Poprawne ID pierwszego zarzutu | 40/40 | 40/40 |
| Prawidłowy pusty plik dokumentu obcego | 8/8 | 8/8 |
| Kontrole dobrane do zmienianego zachowania, fikcyjne PDF-y | 3/8 | 8/8 |

Na czystej kopii commita przeszło 16 testów. W odbiorze rozwojowym `valid_run=true` i `valid_contract=true`. Wszystkie 128 plików wynikowych A3 było identycznych bajt w bajt z A2. Powtórzenie tych samych wejść pod losowymi nazwami (także .PDF) oraz w katalogach i plikach nazwanych inną klasą dało 128/128 + 128/128 identycznych treści JSON i kompletnych rekordów diagnostyki po pominięciu pola ścieżki. Czas CLI na VPS wyniósł 11,53 s dla 128 PDF-ów i 22,92 s dla 256 przemianowań, z polskim OCR dostępnym lokalnie. Proces ekstrakcji działał w izolacji Landlock, bez TCP, etykiet, manifestów i dostępu do zbiorów końcowych.

Pięć odzyskanych prób syntetycznych obejmuje rozszerzony tytuł pełnomocnictwa, umocowanie za pismem przewodnim, odrzucenie cytowanego formularza w instrukcji, pominięcie jawnie wyłączonej czynności oraz parafrazę wykluczenia. Dodatkowy PDF z rzeczywistym obrazem na trzeciej stronie, nazwany `potwierdzenie-przelewu.PDF`, został rozpoznany jako pełnomocnictwo. Pola mocodawcy i pełnomocnika były poprawne. Tesseract odczytał wyłącznie stronę 3 i na nią wskazały dowody pól. Dotychczasowy pokaz klasy dodawanej konfiguracją ponownie przeszedł regresję 11/11 plików i 8/8 negatywów. Poprawa 3/8 → 8/8 dotyczy kontrolowanych przypadków. Skuteczność A3 na nowym zbiorze pozostaje niezmierzona.

## Odtworzenie odbioru rozwojowego

Na VPS z katalogu repozytorium polecenia poniżej wymagają nowego katalogu wyników. `accept_a3.py` przyjmuje wyłącznie wbudowany manifest rozwojowy. Dwie dodatkowe ścieżki dla każdego wejścia wyznacza tylko ewaluator.

```bash
cd ~/uzp-parallel/a3
tools_dir="$HOME/uzp-parallel/rc1-proof/acceptance.4PsV2H5A/tools"
baseline_dir="$HOME/uzp-parallel/rc1-proof/acceptance.4PsV2H5A/development"
dataset_dir="$HOME/uzp-baseline-a/data/uzp"
repeat_dir=$(mktemp -d "$HOME/uzp-parallel/a3-proof/repeat.XXXXXXXX")
PYTHONDONTWRITEBYTECODE=1 "$tools_dir/venv/bin/python" -B -m unittest discover -s evaluation -p 'test_*.py'
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 "$tools_dir/venv/bin/python" -B evaluation/accept_a3.py "$dataset_dir" "$tools_dir" "$baseline_dir" "$repeat_dir/development"
```

Oryginalne dowody są w `~/uzp-parallel/a3-proof/release-e98988f8f0d7/`. Plik `development/summary.json` ma SHA-256 `6dfed7b279ece2acdf9c13a4221e1c0b9e828df062f190de50b85d80441f8d37`. W tym samym katalogu są `synthetics/summary.json`, `real_ocr.py`, `real-ocr.log` i `extension.log`.

## Odbiór po połączeniu prac

W czystej kopii rewizji `5fa11680eac824896839ef4b7f281e1f54b3ed68` połączono A3, opcjonalne adaptery B/C, Compose i demonstrację. Na VPS powtórzono odbiór rozwojowy powyższymi poleceniami z katalogu tej rewizji. Otrzymano TP 1355, FP 5, FN 5 oraz `valid_run=true`. Wszystkie 128 JSON-ów i zbiorcza diagnostyka były identyczne bajt w bajt z A3 sprzed połączenia. Po każdej z dwóch zmian nazw dokumentów 128/128 wyników i rekordów diagnostyki zgadzało się po uwzględnieniu nowej ścieżki.

| Sprawdzenie | Wynik na VPS |
| --- | --- |
| `LANDLOCK=1 PYTHON="$tools_dir/venv/bin/python" sh experiments/abc/test-offline.sh` | 16 testów bazowych oraz 10 testów adapterów i integracji. Oba adaptery dostały identyczny fragment w 10/10 parach. Symulowane awarie zachowały wynik A3. Wywołań rzeczywistych modeli było zero. |
| Natywne CLI i Docker Compose | 6/6 zgodnych wyjść i rekordów diagnostyki, w tym skan odczytany przez polski OCR i pusty plik negatywu. [Procedura odbioru Compose](../../delivery/compose/README.md) |
| Klasa dodana konfiguracją | W profilu z dodatkową klasą zachowano 11/11 plików regresji rozwojowej, w tym 8/8 pustych negatywów. [Pokaz z PDF-em i źródłem pola](../../delivery/final/RAPORT-PROBY.md) |

Na VPS pełne dowody są w `~/uzp-parallel/main-proof/5fa11680eac8/`. Plik `development/summary.json` zawiera wynik ekstraktora, a `offline.log` wynik prób na atrapach dostawców. Odbiór integracji wykorzystywał dane rozwojowe i syntetyczne. Paczka dziesięciu nowych spraw pozostała zapieczętowana.

**Następny krok** to wybór wersji do pojedynczego, odrębnego pomiaru na zapieczętowanych dziesięciu sprawach. Wszystkie powyższe sprawdzenia wykonano lokalnie na VPS bez wywołań LLM.
