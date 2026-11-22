# A3 na polskich potwierdzeniach przelewu

**Na słabych skanach rezerwy KARR mikro-F1 dla sześciu pól wyniosło 41,67% (TP 5, FP 1, FN 13).** A3 poprawnie odczytało kwotę na wszystkich trzech przelewach i datę na jednym. Warunek odbioru z planu wymagał obu pól na obu nowych układach. Spełnił go Millenet. Na potwierdzeniu BNP Paribas zabrakło daty.

## Co zamrożono

Rezerwę zapieczętowano 21 listopada 2026 o 20:32:12 czasu polskiego, przed strojeniem, w rewizji `2241d7e76da99978c6842a3db6a25ae9b0fc8d00`. Do wcześniejszej pary dokumentów KARR doszły dwa polskie układy przelewu. Na obu nowych potwierdzeniach rachunki stron są różne i przechodzą kontrolę sumy NRB. W przykładzie KARR obie strony mają ten sam demonstracyjny numer złożony z zer.

| Materiał źródłowy | Dokumenty w rezerwie |
| --- | --- |
| KARR, ilustracja mBanku | Dotychczasowy przelew i faktura. [Instrukcja KARR](https://karrsa.eu/wp-content/uploads/2023/03/INSTRUKCJA-ROZLICZENIA-POZYCZKI-UNIWERSALNEJ.pdf) |
| BNP Paribas, BiznesPl@net | Potwierdzenie przelewu IMAS International na rzecz Fundacji Siepomaga. [PDF opublikowany przez IMAS](https://imas.pl/wp-content/uploads/2020/06/potwierdzenie_przelewu_Siepomaga_Covid_19.pdf) |
| Bank Millennium, Millenet | Przelew ze strony 2 i faktura pro forma ze strony 1. Kwota na obu stronach jest identyczna. [PDF Fundacji Mam Serce](https://mam-serce.org/wp-content/uploads/2020/05/RESPIRATOR2_proformaprzelew.pdf) |

Każdą z pięciu stron oceniono osobno w trzech postaciach. Z góry wybrany wynik główny dotyczy obrazów 96 dpi w skali szarości, z rozmyciem Gaussa 0,55 px i kompresją JPEG o jakości 55. Pozostałe pomiary obejmują wersje tekstowe oraz czytelniejsze obrazy 129,6 dpi. Kolejne odwzorowania tej samej strony służą ocenie wpływu jakości obrazu. Próba zawiera trzy odrębne przelewy.

Etykiety spisano ze stron przed uruchomieniem ekstraktora na rezerwie. Gold, źródła i manifesty znajdują się poza katalogiem produktu. Nazwy plików wejściowych są neutralne. Dla każdej postaci dokumentów w mianowniku recall jest 18 pól z oczekiwaną wartością. Obie faktury wymagają osobnego pliku o rozmiarze 0 B.

Porównanie SHA-256 wykazało zero wspólnych PDF-ów z bieżącym zbiorem rozwojowym, zestawami UZP `development-40`, `validation-10`, `final-10`, manifestem wcześniejszego testu 10 spraw i wcześniejszym zewnętrznym zestawem rozwojowym. Cztery zgodne hashe z poprzednią rezerwą KARR odpowiadają dwóm zachowanym stronom w wersji tekstowej i skanowanej. Nowe układy pochodzą z dwóch systemów bankowych. Współdzielą elementy typowe dla formularzy przelewu, m.in. prezentację danych obu stron oraz pól daty i kwoty. Rozłączność hashy potwierdza rozłączność plików, a pochodzenie dokumentów pozwala ustalić liczbę niezależnych układów.

## Zmiana A3

Porównano `1503772cbffe5369a4c9bc8548221a445fed7e8e` i `59fcf1a7ef1e506dc3c2e9c5a5c8947b6047aad9`. Dla brakującej kwoty lub daty na skanie A3 odtwarza wiersze z położenia słów Tesseracta. Wiąże wartość z etykietą pola, sprawdza poprawność daty kalendarzowej i daje pierwszeństwo dacie operacji lub wykonania. Aby uzupełnić pole, wymaga zgodności dwóch odczytów albo potwierdzenia całego tokenu liczbowego w wycinkach obrazu. Przy sprzecznych odczytach pozostawia pole puste. Rozpoznanie pominiętego przelewu wymaga współwystąpienia wskazówek bankowych. Ekstraktor pracował bez LLM. Poprawkę strojono wyłącznie na materiale rozwojowym.

## Wyniki

| Zbiór | PDF-y | Mikro-F1 przed | Mikro-F1 po | TP / FP / FN po | Poprawne kwoty po | Poprawne daty po |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rezerwa, słaby skan 96 dpi | 5 | 20,00%* | **41,67%** | 5 / 1 / 13 | 3/3 | 1/3 |
| Rezerwa, skan 129,6 dpi | 5 | 38,46% | 50,00% | 7 / 3 / 11 | 2/3 | 3/3 |
| Rezerwa, PDF z warstwą tekstową | 5 | 72,73% | 72,73% | 12 / 3 / 6 | 3/3 | 3/3 |
| Rozwój, słabe skany | 44 | 69,57%* | 76,19% | 176 / 34 / 76 | 39/42 | 41/42 |

\* Wyniki diagnostyczne starszego A3 z nieważnych przebiegów. Poprzednia wersja wydała pusty plik dla jednego rzeczywistego przelewu na słabej rezerwie i dla czterech przelewów na słabym zbiorze rozwojowym. Poprawiony A3 w tych grupach poprawnie rozpoznał wszystkie dokumenty. Na wszystkich trzech postaciach rezerwy otrzymał `valid_run=true` i `valid_contract=true`. Obie faktury miały po 0 B w każdej postaci.

Na słabej rezerwie precyzja wyniosła 83,33%, a czułość 27,78%. Kwoty poprawiły się z 0/3 do 3/3, a daty pozostały na poziomie 1/3. Mikro-F1 liczone wyłącznie dla kwoty i daty wyniosło 80,00% (TP 4, FP 0, FN 2). Żaden z trzech przelewów nie miał kompletu sześciu prawidłowych pól.

| Układ na słabym skanie | Poprawnie odczytane | Błędne lub pominięte |
| --- | --- | --- |
| KARR | Kwota | Błędny tytuł. Brak daty, numeru transakcji i obu rachunków. |
| BNP Paribas | Kwota | Brak daty, tytułu, numeru transakcji i obu rachunków. |
| Millenet | Kwota, data, rachunek nadawcy | Brak tytułu, numeru transakcji i rachunku odbiorcy. |

Na 44 słabych skanach rozwojowych A3 poprawiło kwotę z 32/42 do 39/42 i datę z 30/42 do 41/42. W obu polach każda wpisana wartość była prawidłowa. W odrębnej regresji na 128 PDF-ach UZP wszystkie 128 plików wynikowych pozostało identycznych bajtowo z `1503772`. Mikro-F1 wyniosło 99,6324% (TP 1355, FP 5, FN 5). Poprawnie rozpoznano po 40 odwołań, pełnomocnictw i przelewów oraz 8 negatywów. Po dwóch niezależnych zmianach nazw (losowych i mylących) wszystkie 128 wyników i diagnostyk pozostało zgodnych w każdej próbie. Wcześniejszy końcowy zbiór pełnych spraw pozostał zamknięty.

## Środowisko, ważność i dowody

Ekstrakcję, testy i scoring wykonano na VPS `hacknation`. Pierwszy pomiar obu rewizji w izolowanym interpreterze bez kontenera zakończył się sygnałem 11 (`SIGSEGV`) przed zapisaniem pierwszego wyniku. Obie próby są nieważne. Przyczyna awarii pozostaje nieustalona. Następnie wersję bazową i kandydata uruchomiono w dostarczanym przez projekt Docker Compose na tym samym serwerze, z wyłączoną siecią, na tych samych rewizjach i danych. Pomiędzy próbami kod i etykiety zachowały te same hashe. Tabela rezerwy pochodzi z tego powtórzenia technicznego. Liczby przeliczono też z zapisanych JSON-ów za pomocą `evaluation/score.py`.

Na VPS przeszły oba zestawy testów, liczące 33 i 10 przypadków. Testy integracji z dostawcami używały atrap. Dodatkowe porównanie sześciu skanów rozwojowych potwierdziło bajtową zgodność wyników Compose z wynikami uruchomienia bez kontenera.

Metadane użyte do odbioru są w [indeksie pomiaru](../../evaluation/przelewy-karr-v2.json). Na VPS w `~/uzp-parallel/a3-przelewy-dane/karr-v2/` znajdują się `audit.json`, `candidate.json`, manifesty, wyniki, diagnostyki i logi obu prób. Archiwum `pakiet-karr-v2.tar.gz` ma SHA-256 `75d5f0f7926ed3e6cc8e30e56e05dc2c370b5dfe65e0c351fc102415036e9e65`. Pieczęć `corpus/seal.json` ma SHA-256 `7e18c2361a8d22b03a99c691330a9fc9a657665a6e72c56901c58a55ad7687ee`.

Ponowne obliczenie głównej metryki z już zapisanych wyników na VPS jest możliwe tym poleceniem.

```sh
cd ~/uzp-parallel/a3-przelewy
dane=~/uzp-parallel/a3-przelewy-dane/karr-v2
narzedzia=~/uzp-parallel/rc1-proof/acceptance.4PsV2H5A/tools
"$narzedzia/venv/bin/python" -B evaluation/score.py "$dane/corpus" \
  "$dane/measurements/compose-reserve-candidate/reserve_weak/output" \
  --manifest "$dane/corpus/manifests/reserve_weak.json"
```

**Następny krok.** Zdiagnozować `SIGSEGV` w ścieżce bez kontenera na osobnym materiale rozwojowym. Odbiór wymaga, aby obie ścieżki uruchomienia ukończyły cały reprodukujący problem folder i zapisały identyczne wyniki. Po ujawnieniu wyniku KARR v2 może służyć do sprawdzania regresji. Kolejny niezależny pomiar jakości wymaga nowych odłożonych dokumentów.
