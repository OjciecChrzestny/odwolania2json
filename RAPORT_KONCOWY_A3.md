# Jednorazowy test końcowy A3 na skanach UZP

10 pełnych spraw, 30 PDF-ów, 21.11.2026 18:30 czasu warszawskiego. Ścisłe mikro-F1 na polach wyniosło **0,5567010309 (55,67%)**. Miernik z mierzonego commita zwrócił **`valid_run=false`**, a osobny walidator **`valid_contract=true`**. Precyzja wyniosła 76,70%, a czułość 43,69%.

| Klasa wzorcowa | Poprawna klasa | TP | FP | FN | Mikro-F1 pól |
| --- | ---: | ---: | ---: | ---: | ---: |
| Odwołanie | 10/10 | 97 | 34 | 80 | 62,99% |
| Pełnomocnictwo | 10/10 | 37 | 6 | 41 | 61,16% |
| Potwierdzenie przelewu | 2/10 | 1 | 1 | 53 | 3,57% |
| **Razem** | **22/30** | **135** | **41** | **174** | **55,67%** |

A3 zapisał 30 plików i zgłosił 0 błędów odczytu. Osiem prawidłowych potwierdzeń przelewu otrzymało klasę dokumentu obcego i pliki długości 0 B. Dla tych przelewów miernik oczekiwał obiektów JSON, zapisał osiem błędów parsowania i policzył utracone pola jako FN. Walidator formatu zaakceptował wszystkie wyniki w ich przewidzianych klasach. Klasa wzorcowa zgadzała się w 22/30 PDF-ach. Na poziomie punktowanych pól żaden dokument nie miał kompletu poprawnych wartości. Paczka zawierała po dziesięć dokumentów trzech klas i zero rzeczywistych negatywów.

## Rozkład błędów

- **Przelewy.** Osiem pustych wyników kosztowało 42 FN. Także w dwóch rozpoznanych przelewach zabrakło kwoty, daty i obu rachunków. Z 54 wzorcowych wartości we wszystkich przelewach poprawny był jeden tytuł. Drugi wydobyty tytuł różnił się od wzorca.
- **Odwołania.** Klasyfikacja trafiła 10/10. W każdym odwołaniu selektor zapisał regułę `brak_jednoznacznej_reguły_czynności` i nadał awaryjne ID 11. W jednej sprawie wzorzec miał ID 11. Dziewięć błędnych ID dało również dziewięć błędnych opisów słownikowych. We wszystkich odwołaniach zabrakło daty zaskarżonej czynności, a w dziewięciu oczekiwanych polach zabrakło e-maila pełnomocnika. Wszystkie numery postępowań były poprawne. Każde odwołanie miało 4–7 stron. Diagnostyka odnotowała OCR stron 1 i 2 w każdym z nich. Sam zapis pomiaru nie ustala położenia pierwszego zarzutu w konkretnym PDF-ie.
- **Pełnomocnictwa.** Klasyfikacja trafiła 10/10. Ekstraktor pominął wszystkie 17 oczekiwanych imion i nazwisk pełnomocników i wszystkie 14 imion i nazwisk osób podpisujących. Prawidłowo wydobył 11/11 wartości NIP i 10/10 wartości KRS mocodawców.
- **Bilans pól.** Miernik znalazł 135 dokładnych trafień, 135 brakujących wartości, 39 podstawień i 2 wartości nadmiarowe. Podstawienie daje jednocześnie FP i FN. Sumy wynoszą 135 TP, 41 FP i 174 FN.

## Warunki i dowody

| Pozycja | Wartość |
| --- | --- |
| Mierzony commit | `5de75693429d9699368b958cd54eda4dd76e4900` |
| Rewizja danych | `84cc976f0a9af5cee14f131c795f929134ca0fda` |
| SHA-256 zamrożonego manifestu | `a87ed39171b9191f32a089b9e6490f4e2e3cc2c954b8feecd97c836a0bbc5dbf` |
| Obraz rootless Docker na VPS | `sha256:4d0a7dc54873b5965ad0124a668231fc6df36502b8871b7bf6e99391e869b190` |
| Wykonanie | Jedno uruchomienie CLI A3, lokalny polski OCR, 0 wywołań LLM, sieć kontenera wyłączona. Czas od startu do zakończenia kontenera wyniósł 58,347 s. |
| Zakres OCR | Diagnostyka odnotowała 40 stron w 30 PDF-ach. |
| Kody wyjścia | Ekstraktor 0, miernik `evaluation/score.py` 1, walidator `evaluation.check_outputs` 0. |

Przed uruchomieniem porównano kod i konfiguracje z obrazu z plikami w czystej kopii mierzonej rewizji. Zweryfikowano sumy kontrolne paczki i polskich danych OCR. Do kontenera zamontowano neutralnie nazwane PDF-y oraz katalogi na wyjścia i diagnostykę. Etykiety i manifest były dostępne tylko procesom przygotowania i oceny na hoście. Sumy wyników zapisano po wyjściu kontenera, przed uruchomieniem miernika. Integralność paczki i wyników sprawdzono ponownie po analizie błędów.

Na VPS prywatne dowody są w `/home/dev-viralpay/uzp-parallel/odbior-koncowy-prywatne/a3-10-84cc976`. Poniższe polecenie sprawdza istniejące pliki bez powtarzania ekstrakcji.

```sh
ssh hacknation 'cd /home/dev-viralpay/uzp-parallel/odbior-koncowy-prywatne/a3-10-84cc976 && sha256sum --quiet -c wyniki.sha256 && sha256sum --quiet -c predictions.sha256 && cat status.json'
```

`score.json` zawiera wynik miernika, `contract.json` macierz klasyfikacji, `summary.json` liczniki błędów według pola i decyzje o ID, a `coverage.json` liczbę stron w każdym PDF-ie i zakres OCR.

**Następny krok** to odtworzenie braków przelewów i zakresu OCR odwołań na oddzielnych skanach rozwojowych. Te dziesięć spraw ma już znany wynik A3. Kolejna niezależna ocena wymaga nowej próby.
