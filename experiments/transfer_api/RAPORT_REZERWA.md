# Przelewy A3 i Scaleway na niezależnej rezerwie

**Decyzja.** Wariant z API pozostaje eksperymentalny. Wśród trzech publicznych potwierdzeń żaden wariant nie zwrócił kompletu pól. Jedynym zyskiem na rezerwie była poprawnie odczytana słowna data w dokumencie syntetycznym.

## Wyniki

| Zbiór | A3 | A3 + brakująca kwota | A3 + brakująca kwota i data | Ważność lokalnego pomiaru |
| --- | ---: | ---: | ---: | --- |
| Rozwojowe słabe skany, 44 PDF-y | 76,19% | 76,99% | 77,25% | Wszystkie trzy ważne |
| Rezerwa publiczna, 3 przelewy i 2 negatywy | 27,27% | 27,27% | 27,27% | Miernik odrzucił przebieg dla każdego wariantu |
| Rezerwa syntetyczna, 3 przelewy | 96,97% | 96,97% | 100,00% | Wszystkie trzy ważne |
| Cała rezerwa, 8 PDF-ów | 69,09% | 69,09% | 71,43% | Wyniki diagnostyczne |
| Regresja UZP, 128 rozwojowych PDF-ów | 99,63% | 99,63% | 99,63% | Wszystkie trzy ważne |

Kolejne wartości TP, FP i FN dla całej rezerwy to 19/2/15, 19/2/15 i 20/2/14. Dla części publicznej każdy wariant dał 3/2/14. Na trzech dokumentach syntetycznych A3 i wariant kwotowy dały 16/0/1, a oba pola z API 17/0/0. Przy jednym przelewie, dla którego wydruk zawierał wyłącznie datę wygenerowania, wariant daty zachował poprawne pole puste.

**Ważność.** Compose zakończył przetwarzanie i zapisał osiem wyników. Oba negatywy dostały pliki długości 0 B. A3 potraktował też jako negatyw rzeczywiste potwierdzenie z BIP Konstancina-Jeziorny. Dla pozytywu miernik w **evaluation/score.py** wymaga obiektu JSON. Pusty plik spowodował błąd odczytu i ustawienie **valid_run=false** w części publicznej i całej rezerwie. **check_outputs** zaakceptował spójność formatu z klasą rozpoznaną przez CLI. Pełne porównanie odpowiedzi API ma osobny znacznik **valid_model_comparison=false**, ponieważ odpowiedź dotycząca publicznej kwoty nie przeszła walidacji. [Potwierdzenie opublikowane w BIP](https://bip.konstancinjeziorna.pl/attachments/download/15848)

**Źródła błędów.** Na wzorze MPGK A3 odczytał datę. Wycinek kwoty wyraźnie zawierał 52,60. Scaleway odpowiedział HTTP 200, ale program odrzucił odpowiedź i pozostawił kwotę pustą. Archiwum zawiera skrót odpowiedzi, więc konkretna przyczyna błędu formatu pozostaje nieustalona. Na potwierdzeniu Muzeum A3 poprawnie podał kwotę i datę, do tytułu dopisał fragment etykiety, błędnie odczytał znak referencji bankowej i pominął oba rachunki. Do API kwalifikują się wyłącznie puste pola kwoty i daty w rozpoznanych przelewach. [Wzór MPGK](https://www.mpgk.com.pl/download/przykladowe-potwierdzenie-przelewu,39.pdf/view) · [Załącznik do odwołania, strona 11](https://muzn.pl/wp-content/uploads/2024/12/9a5a1ed0-odwolanie-wraz-z-zalacznikami.pdf#page=11)

**Rozwój i regresja.** Na 44 znanych skanach A3 dał 176/34/76, wariant kwotowy 179/34/73, a oba pola 180/34/72. Na jednym polu A3 pozostawił pustą datę, wcześniejszy pilot podał dzień wydruku 22.07.2026, a nowy odczytał 21 lipca 2026 z wiersza operacji. Poza tym wykorzystano trzy uprzednio zapisane odpowiedzi kwotowe, zweryfikowane skrótem całego żądania. Regresja na 40 odwołaniach, 40 pełnomocnictwach, 40 przelewach i 8 negatywach dała 1355/5/5. Wszystkie 128 plików wynikowych w każdym wariancie było bajtowo zgodnych z poprzednim A3. Żaden dokument tej regresji nie wymagał wywołania API.

## Zamrożenie i pomiar

Pieczęć **d616d59c1d2905b04210c5a8c1e40abb30f3f9cae3087596f51947bda09d0335** powstała 21 listopada 2026 o 21:19:37 UTC, przed zmianą kodu. Indeks został utrwalony w **5f8b34b**. Oceniany kod ma rewizję **80ad377a30ee422bd378a6ae85ae4b57db41fe61**. Obraz Compose zawiera identyczne pliki produktu jak A3 **59fcf1a**. Jeden dokument daje jeden głos w zbiorze. Na wejście trafiła wyłącznie wersja rastrowa 96 dpi z rozmyciem 0,55 px i kompresją JPEG 55. PDF-y i wzorce znajdują się na VPS poza repozytorium i poza wejściem ekstraktora.

Na trzech publicznych układach znalazły się miejski wzór MPGK oraz dwa różne wydruki z Aliora. Potwierdzenie natychmiastowe i odpis KRS pochodzą z jednego publicznego pliku i zajmują rozłączne strony. Drugim negatywem jest pełny, niewypełniony blankiet wpłaty. Trzy autorskie próby syntetyczne sprawdzają układ dat w wierszach, w kolumnach oraz przypadek z samą datą wygenerowania. Poprzednio występujące układy mBanku i Pekao24 zostały wykluczone. [Blankiet Polskiej Fundacji dla Afryki](https://pomocafryce.org/wp-content/uploads/2020/08/przekaz-pfda.pdf)

Przecięcia SHA-256 źródeł, dokumentów wydzielonych i nowych skanów ze zbiorami development-40, validation-10, final-10, poprzednim holdoutem 10 spraw, external-v1, rezerwami KARR i wcześniejszymi plikami źródłowymi wyniosły zero. W porównaniu ze 129 różnymi skrótami znormalizowanej pierwszej strony starych korpusów zewnętrznych nie powtórzył się żaden obraz. Dwa układy tego samego banku i wspólne pochodzenie dwóch załączników ograniczają niezależność. [Indeks zamrożenia](../../evaluation/przelewy-rezerwa-v3.json)

Na VPS A3 przetworzył osiem PDF-ów w 17,78 s. Przygotowanie obrazów zajęło 2,62 s, a zastosowanie obu pól z API 13,52 s. Łącznie 33,92 s. Wariant kwotowy odtworzono z tej samej odpowiedzi, bez osobnego pomiaru czasu pełnego przebiegu. Do Scaleway wysłano dwa sprawdzone wycinki rezerwy oraz jeden rozwojowy. Wszystkie trzy otrzymały HTTP 200. Łącznie zużyły 733 tokeny wejścia i 85 wyjścia, co daje około 0,000140 € według stawek katalogowych przed podatkami i darmową pulą. [Cennik Scaleway](https://www.scaleway.com/en/pricing/model-as-a-service/)

## Odtworzenie na VPS

Polecenia odczytują zapisane predykcje bez dostępu do klucza. Pierwszy skrót powinien wynieść **bd5a4d8138737404cdc6612ca61a0e14a30956acfb7143e4af2a938dc35f09c0**.

~~~sh
cd ~/uzp-parallel/przelewy-api
dane=~/uzp-parallel/a3-przelewy-dane
partia="$dane/przelewy-rezerwa-v3"
py=~/uzp-parallel/rc1-proof/acceptance.4PsV2H5A/tools/venv/bin/python
set -o pipefail
"$py" -B -m experiments.transfer_api.benchmark --dataset "$partia/corpus" --run "$partia/holdout" | sha256sum
cat "$partia/holdout/report.json"
diff -qr "$dane/karr-v2/measurements/regression-128-release/neutral/output" "$partia/regression128/C/output"
cat "$partia/regression128/report.json"
~~~

**Następny krok.** Zebrać oddzielne rozwojowe skany bankowych potwierdzeń i podobnych pustych druków. Poprawić rozpoznawanie wykonanego przelewu na podstawie treści i związku między etykietami kwoty, daty i stron. Warunkiem odbioru jest JSON dla każdego dodatniego przykładu w nowej próbie, 0 B dla jej negatywów i utrzymanie regresji 128/128. Ocenę generalizacji po zmianie przeprowadzić na kolejnym, wcześniej zamrożonym zbiorze.
