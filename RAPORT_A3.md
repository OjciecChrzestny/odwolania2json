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
