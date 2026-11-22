# Wyniki jakości i tryb offline

Miara to mikro-F1 pól. TP, FP i FN oznaczają poprawne trafienia, fałszywe trafienia i pominięcia.

| Próba | TP / FP / FN | Mikro-F1 | Status |
| --- | --- | --- | --- |
| DEV128 | 1359 / 1 / 1 | 99,9265% | Regresja deweloperska na znanym zbiorze |
| Historyczne znane30 | 152 / 45 / 157 | 60,08% | Przebieg nieważny |
| Złożony wariant F198, `f1987cb38e0db7a43f8868d03eeedda450caf0d7` | 281 / 12 / 28 | 93,36% | Ważny przebieg na jawnej puli, pierwsze ID 10/10 |

Publiczne 30 PDF-ów wykorzystano do strojenia. Dawne próby 7+4 są raportowane osobno jako pomiary historyczne. Wynik na tajnym zbiorze pozostaje nieznany. Wynik zmierzony na finalnym SHA i paczce oraz raport z każdej niezależnej próby znajdą się w `RAPORT-KONCOWY.md` obok archiwum wydania.

## Pomiary wariantu z automatycznym odczytem kwoty

W historycznej próbie 44 słabych skanów uzupełnianie brakującej kwoty przez Scaleway poprawiło F1 sześciu pól z 76,19% do 76,99%. Najnowsza integracja z trwałym limitem 1 EUR została wdrożona bez nowego przebiegu jakościowego. Wyniki wcześniejszego wydania opisuje jego [raport](https://github.com/OjciecChrzestny/odwolania2json/releases/tag/v2026.11.22-uzp). [Zakres historycznego porównania](../experiments/transfer_api/RAPORT_REZERWA.md)

## Szybkie sprawdzenie obrazu bazowego

Wybrany profil regułowy używa lokalnego OCR i działa bez klucza API. Poniższe polecenie sprawdza pełny SHA i ID przygotowanego obrazu.

```sh
docker image inspect odwolania2json-jury:final-20261122 \
  --format '{{index .Config.Labels "org.opencontainers.image.revision"}} {{.Id}}'
```

W osobnym katalogu próby umieść [syntetyczny skan](../delivery/compose/skan-syntetyczny.pdf) w `input/`. Wykonaj [blok RUN.md](../RUN.md) z `--pull=never` i `--network=none`. Wynik i źródło pola znajdziesz w `output/` i `diagnostics/last-run.json`.
