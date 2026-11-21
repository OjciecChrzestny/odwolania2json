# Dopuszczenie źródeł do porównania 06

`protocol_06.json` zachowuje SHA-256 `7d64c49b84df3ab2fc627c5ee8cd807201646bef54561d1f397813b4c879536a` i definicje pomiaru. To uzupełnienie opisuje format danych dla kustosza 01 i koordynatora. Syntetyczny tryb pozwala sprawdzić format bez użycia rezerwy.

## Specyfikacja porównania

W pliku `--spec` tryb `production` podaje `source_seal` z polami `path` i `sha256` (hash surowych bajtów pieczęci 01), oraz obiekt `cohorts` z wpisami `known_128`, `blind_full_cases`, `blind_transfers` i `page_review`.

- Wpis gotowy ma `status: "ready"`, `dataset`, `manifest`, `manifest_sha256` i `labels`. Wartość `human` poświadcza niezależne oceny pól i stron. `unavailable` oznacza brak takich ocen. Pomiar pól w pozostałych kohortach nadal korzysta z referencji przypiętych przez manifest.
- Wpis niedostępny ma `status: "unavailable"` i `reason`. Ten sam stan i powód figurują w pieczęci 01. Taki wpis nie potrzebuje ścieżek ani manifestu i nie generuje wyniku. Nadal figuruje w `admission` i końcowym porównaniu.
- W `page_review` porównaj niezależny stan wszystkich stron. Gotowy wpis wymaga `human`, ocen w `documents[].pages` w manifeście i zgodności z liczbą stron poświadczoną w pieczęci. Brak kompletu pozostawia kohortę niedostępną z przyczyną.
- Surowe dane pozostają w katalogach przygotowanych przez kustosza. Manifest oceny wskazuje neutralny `input`, plik `pdf`, jego `sha256`, klasę i referencję zgodnie z istniejącym `score.py`. Zadanie 06 sprawdza pieczęć przed odczytem manifestów. Etykiety pól trafiają do oceny po zapisaniu wyjść obu wariantów.

## Pieczęć źródeł 01

Kustosz dostarcza dokument JSON o `version: 1` z polami `custodian: "01"`, `base_sha` i `sealed_utc`. W `control_inventory` podaje tablice `pdf_sha256`, `source_sha256` i `template_families` dla znanych źródeł, DEV i rodzin kontrolnych. `cohorts` zawiera cztery wpisy. Wpis gotowy ma `status: "ready"`, identyczny `manifest_sha256`, identyczne `labels` oraz listę `documents` dopasowaną po neutralnym `input`. Każdy rekord pochodzenia zawiera:

- `input` i `pdf_sha256` użytego PDF-u.
- `source_sha256` pierwotnych bajtów przed pocięciem, rasteryzacją lub zmianą formatu.
- `source_document_id` kanonicznego dokumentu, wspólny dla jego kopii i fragmentów.
- `template_family` według wspólnej ewidencji kustosza.
- `case_id` w pełnych sprawach i `page_count` w pomiarze stron.

Wpis `blind_full_cases` dodatkowo zawiera mapę `cases` z rekordami `{"source_case_id": "<kanoniczny identyfikator z pierwotnego źródła>", "authentic": true}` pod kluczami `case_id`. Parser sprawdza unikalność kanonicznych spraw, trzy klasy w każdej sprawie i minimum 10 kompletnych spraw. Sprawdza też obecność negatywu. Kustosz odpowiada za ustalenie autentyczności, identyfikację oryginałów oraz tożsamość rodzin. Skrót pieczęci wiąże jego poświadczenie z porównaniem.

Mechanizm odrzuca powtórzone hashe użytych PDF-ów między kohortami, powtórzone źródła między kohortami albo sprawami oraz domieszanie rodzin i hashy z ewidencji kontrolnej do ślepej próby. W obrębie jednej pełnej sprawy różne kanoniczne dokumenty mogą pochodzić z jednego pierwotnego pliku sprawy. Wspólne rodziny między dwiema ślepymi kohortami są wykazywane w ewidencji dopuszczenia, przy zachowaniu rozłączności źródeł i PDF-ów.

Niezgodność integralności blokuje zapieczętowanie. Brak zakresu lub kompletu ocen obniża kohortę do `unavailable` z powodem. `run` odtwarza decyzję z tej samej pieczęci i manifestów przed utworzeniem znacznika próby. Przebieg produkcyjny pozostaje osobnym działaniem koordynatora.
