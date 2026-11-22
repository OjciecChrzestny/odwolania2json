# A2 — rozpoznawanie przelewów

A2 obsługuje potwierdzenie przelewu z nagłówkiem rozbitym na dwa wiersze tej samej strony. Nowa alternatywa w sygnale `nagłówek_przelewu` wymaga, aby ostatni wiersz kończył się słowem „przelewu” albo „przelewu krajowego”. Waga sygnału, próg i reguły ekstrakcji są takie jak w A.

## Odbiór syntetyczny

Niezależny test generuje sześć przelewów z fikcyjnymi danymi. Obejmuje m.in. polecenie przelewu, potwierdzenie transakcji z nazwą banku w tym samym wierszu, potwierdzenie operacji bankowej i dwa miejsca złamania nagłówka. A zapisał 0 bajtów dla obu złamanych nagłówków. A2 zwrócił zgodne obiekty ze wszystkimi sześcioma polami, zachowując kierunek rachunków.

Wezwanie do zapłaty z numerem rachunku i kwotą oraz instrukcja z podobnym zwrotem i przykładem wypełnienia dały po 0 bajtów w obu wariantach. Cały zestaw ośmiu testów A2 przeszedł na Pythonie 3.13.18.

## Porównanie na 128 PDF-ach rozwojowych

| Miara | A | A2 |
| --- | ---: | ---: |
| Poprawnie rozpoznane przelewy | 40/40 | 40/40 |
| Ścisłe mikro-F1 dla przelewów | 1,0000 | 1,0000 |
| Fałszywe rozpoznania na dokumentach obcych | 0/8 | 0/8 |
| Wyniki zgodne z kontraktem | 128/128 | 128/128 |
| TP / FP / FN | 1355 / 5 / 5 | 1355 / 5 / 5 |
| Ścisłe mikro-F1 | 0,9963235294 | 0,9963235294 |

Oba przebiegi miały `valid_run=true`. A2 odzyskał **0** przelewów rozwojowych i wprowadził **0** nowych fałszywych rozpoznań na 88 dokumentach innych klas. Drzewa 128 wyników są identyczne bajt w bajt. W tym zbiorze A poprawnie rozpoznawał już wszystkie przelewy.

Porównano na VPS commity `19f702fc58e685f85f2fae14557d14f2c5453cfd` (A) i `d04fe1b816df09782d9c893541fe7cd29b461068` (A2) przy danych UZP `de135d20811caf630f3e94dc655ba5eebd9a6710`. Każdy przebieg uruchomiono osobno przez `evaluation/run_private_linux.sh` z nowym neutralnym wejściem przygotowanym z `evaluation/development-40.json`. Wyniki policzył oryginalny `evaluation/score.py` z jawnym manifestem rozwojowym. Diagnostykę obu przebiegów i porównanie zapisano na VPS w `/home/dev-viralpay/uzp-baseline-a/runs/przelewy-a2`.

```sh
python -m unittest discover -s evaluation -p 'test_przelew_headers.py'
python -m unittest discover -s evaluation -p 'test_*.py'
```

**Granica wniosku.** Regresja potwierdza poprawę na syntetycznych nagłówkach. Przyczyna błędu z zamrożonego pomiaru A pozostaje nierozstrzygnięta. Ten etap objął wyłącznie syntetyki i zbiór rozwojowy. [Zachowany raport A](RAPORT_A.md)

**Następny krok.** Zachować test regresji przy wyborze kolejnego kandydata do pomiaru.
