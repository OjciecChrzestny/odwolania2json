# Pomiar A3 z Mistralem dla przelewów

**Scaleway przyjął klucz.** Model `mistral-small-3.2-24b-instruct-2506` prawidłowo odczytał fikcyjną kwotę 17,42 PLN oraz wszystkie trzy brakujące kwoty w próbie rozwojowej. Jedyna próba uzupełnienia daty dała datę wygenerowania dokumentu. Mikro-F1 sześciu pól wzrosło z 76,19% do 76,82%. Przetworzenie tej samej partii zajęło odpowiednio 51,92 s i 86,93 s.

## Przebieg i zakres

Pomiar przeprowadzono na VPS `hacknation` 21 listopada 2026 w godz. 22:03–22:04 czasu polskiego. Oba warianty współdzieliły ten sam przebieg A3 w Docker Compose z rewizji `59fcf1a7ef1e506dc3c2e9c5a5c8947b6047aad9`. Partia obejmowała 42 słabe skany przelewów i dwa negatywy. Manifest `dev_weak.json` miał SHA-256 `1497dbc5166ee4f8e65558f2e09c79d3995183859f0b1e25b8daabe6a8862c1d`. Ponowne uruchomienie A3 odtworzyło bajtowo 44/44 zapisanych wyników. Odtworzone cztery obrazy i ich współrzędne były zgodne z zamrożoną kolejką.

Po A3 dodatkowy czytnik uruchamiał się tylko dla pustej kwoty lub daty w rozpoznanym przelewie. Na zewnętrzne API trafiły cztery obrazy wybranych komórek liczbowych i wyłącznie etykiety z ustalonej listy. Wszystkie cztery dokumenty źródłowe pochodziły z publicznego rozwojowego zbioru UZP. Selekcja i budowa żądań korzystały z obrazu i predykcji A3. Referencje otworzył dopiero miernik. Rezerwa KARR i końcowy zbiór pełnych spraw pozostają do odrębnych zastosowań. Eksperyment dotyczy przelewów. Planowane porównanie ID pierwszego zarzutu w odwołaniach wymaga osobnego przebiegu.

Przed próbą na dokumentach wykonano dwa wywołania z tym samym sztucznym obrazem. Pierwsze uzyskało HTTP 200, ale walidator odrzucił format odpowiedzi. Drugi zapis potwierdził odczyt `17,42` w prawidłowym wierszu. Przed zamrożeniem kandydata dostosowano walidację polskiego separatora dziesiętnego do istniejącej normalizacji A3. Poprawkę sprawdzono na już zapisanej odpowiedzi. Po zamrożeniu wykonano po jednym żądaniu na każde z czterech pól. Wszystkie cztery zakończyły się HTTP 200.

## Wyniki na 44 PDF-ach

| Pomiar | A3 | A3 + Scaleway |
| --- | ---: | ---: |
| Ścisłe mikro-F1 wszystkich sześciu pól | 76,19% | 76,82% |
| TP / FP / FN | 176 / 34 / 76 | 179 / 35 / 73 |
| Poprawne kwoty | 39/42 | 42/42 |
| Poprawne daty operacji | 41/42 | 41/42 |
| Błędne wpisane daty | 0 | 1 |
| Kompletne przelewy | 3/42 | 3/42 |
| Trafienia klasy / negatywy z plikiem 0 B | 44/44 · 2/2 | 44/44 · 2/2 |
| Czas od startu CLI do zapisania wyniku | 51,92 s | 86,93 s |

Oba przebiegi spełniły test `valid_run` i kontrakt wyjścia. Spośród 44 JSON-ów 40 pozostało identycznych bajtowo. W pozostałych czterech porównanie wszystkich pól potwierdziło, że zmieniła się tylko właściwa pusta komórka. Hybryda zwiększyła mikro-F1 o 0,63 pkt proc. i wydłużyła pracę o 35,01 s. Przygotowanie obrazów zajęło 5,56 s, a etap z API 29,44 s, w tym 29,23 s na cztery połączenia. Czas odczytano z jednego wspólnego przebiegu od wejścia PDF do wyjścia JSON. Scoring i dwie osobne próby techniczne są liczone poza tym czasem.

Model uzupełnił kwoty 200,00 PLN, 200,00 PLN i 50,00 PLN. W `case_52/doc_03.pdf` podał `2026-07-22`. W warstwie tekstowej pierwotnego dokumentu te same współrzędne wskazują `22.07.2026` w wierszu „wygenerowano”. Właściwe pole „Data operacji” ma wartość `21 lipca 2026`. Selektor obrazu rozpoznawał daty liczbowe i przekazał jeden wiersz bez etykiety. Rzeczywista data operacji nie trafiła do modelu. Po zakończeniu próby przeliczono z zapisanych JSON-ów wariant wykorzystujący wyłącznie trzy odpowiedzi kwotowe. Dał 76,99% (179 / 34 / 73) na tym samym zbiorze. To dodatkowa analiza rozwojowa. [Dokument źródłowy w przypiętej rewizji UZP](https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/de135d20811caf630f3e94dc655ba5eebd9a6710/dane/przyklad_52/potwierdzenie_przelewu.pdf)

Na czterech wycinkach Scaleway wykazał 1200 tokenów wejścia i 108 wyjścia. Ze sztucznymi próbami było 1878 tokenów wejścia i 158 wyjścia. Przy stawkach katalogowych 0,15 € za milion tokenów wejścia i 0,35 € za milion tokenów wyjścia nominalna wartość tokenów wyniosła odpowiednio 0,000218 € i 0,000337 €. Rzeczywista faktura uwzględnia darmowy limit i reguły rozliczeń operatora. [Cennik Scaleway](https://www.scaleway.com/en/pricing/model-as-a-service/) · [Zasady rozliczeń](https://www.scaleway.com/en/docs/generative-apis/faq/#how-does-the-free-tier-work)

## Odtworzenie wyniku bez opłat API

Stosowane przez projekt narzędzia `evaluation/score.py` i `evaluation/check_outputs.py` ponownie obliczają miary i ważność z zapisanych drzew. Na VPS można uruchomić poniższe polecenie.

```sh
cd ~/uzp-parallel/przelewy-api
dane=~/uzp-parallel/a3-przelewy-dane
pomiar="$dane/llm-przelewy-v1/api/scaleway-pilot-1"
python_uzp=~/uzp-parallel/rc1-proof/acceptance.4PsV2H5A/tools/venv/bin/python
"$python_uzp" -B -m experiments.transfer_api.compare --dataset "$dane/karr-v2/corpus" \
  --manifest "$dane/karr-v2/corpus/manifests/dev_weak.json" --run "$pomiar/live-44"
```

W katalogu `$pomiar` zapisano pieczęć kodu i obrazów w `candidate.json`, podsumowanie i sumy kontrolne w `results.json` oraz test syntetyczny. `live-44/comparison.json` zawiera porównanie per pole, `live-44/timing.json` czasy ścienne, a `live-44/one-date-evidence.json` pozycję w źródłowym PDF-ie. Surowe PDF-y, wycinki i rzeczywisty klucz pozostają poza repozytorium. Na VPS przeszło 13 testów offline obejmujących normalizację, przerwanie dalszych wywołań po 429 przy zachowaniu wyniku A3, czytnik przelewów i miernik.

**Następny krok.** Zamrozić niezależną partię polskich przelewów z różnych układów, w tym z datą operacji zapisaną słownie i inną datą wygenerowania. Następnie na danych rozwojowych dołączyć etykietę „Data operacji” i daty słowne do wyboru wycinka. Przy braku podstawy do wyboru zachować `null`. Porównać na nowej partii A3, wariant uzupełniający wyłącznie kwoty oraz wariant z udokumentowaną datą. Decyzję o włączeniu do CLI oprzeć na tym porównaniu, poprawności negatywów i czasie całej partii.
