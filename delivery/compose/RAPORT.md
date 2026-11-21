# Odbiór Docker Compose na VPS

Próba z 21 listopada 2026 r. potwierdziła natywne CLI z polskim OCR i rozwiniętą konfigurację Compose. Odbiór kontenerowy czeka na działający Docker Engine na VPS `hacknation`.

| Identyfikator | Wartość |
| --- | --- |
| Gałąź | `codex/uzp-compose` |
| SHA kodu sprawdzonego w próbie | `89173324f8a20a40097f5a5f1d859afa11251e01` |
| SHA mierzonego A | `19f702fc58e685f85f2fae14557d14f2c5453cfd` |
| Rewizja danych rozwojowych | `de135d20811caf630f3e94dc655ba5eebd9a6710` |
| Host | Ubuntu 24.04 LTS, Linux 6.8.0-31-generic, x86-64, 6 vCPU, 23,46 GiB RAM |
| Natywne środowisko | Python 3.13.18, pypdf 6.21.4, pypdfium2 5.15.2, tesserocr 2.13.0 |
| Narzędzia Docker | klient 29.1.3, Compose 2.40.3, Buildx 0.30.1 |

Pakiet CLI, konfiguracja klas i oba pliki zależności są identyczne z mierzonym A według `git diff --exit-code 19f702fc58e685f85f2fae14557d14f2c5453cfd HEAD -- odwolania2json requirements.txt requirements-ocr.txt`. Zestaw zawiera cztery PDF-y z `case_10`, kopię przelewu o tej samej nazwie w innym podkatalogu i syntetyczny jednostronicowy skan przelewu bez warstwy tekstowej. Przygotowanie sprawdza rewizję UZP i hashe wejść z manifestu rozwojowego.

## Wykonane sprawdzenia

| Próba | Wynik |
| --- | --- |
| Natywne CLI we własnym folderze ze spacją | 6 PDF-ów, 6 wyników, 0 błędów odczytu, 0,796 s |
| Natywny pusty folder | 0 wyników, pusta diagnostyka, 0,251 s |
| Trzy klasy i negatyw | Oczekiwane klasy z manifestu, `case_10/doc_02.json` ma dokładnie 0 B |
| Dwie identyczne nazwy | Pliki w `case_10/` i `duplikat/` mają identyczne bajty |
| Polski OCR | SHA-256 `pol.traineddata` zgodny z README. Skan dał `kwota=123.45`, `tytul="Opłata za usługę"` i `ocr_pages=[1]`. |
| Natywna ewidencja w osobnych procesach | Po usunięciu jednego wejścia zniknął jeden stary JSON. Bajty pozostałych wyników i plik ręczny zostały zachowane. |
| Regresja A | 7 testów, 0 błędów |
| `docker compose config --format json` | Poprawne montowania dla domyślnych, jawnych domyślnych i własnych ścieżek ze spacjami. Konfiguracja ustawia wejście tylko do odczytu, tryb sieci `none` i osobne ścieżki wyjścia, ewidencji i diagnostyki. |

`docker version` zwróciło tylko dane klienta i ten błąd połączenia z serwerem:

```text
failed to connect to the docker API at unix:///var/run/docker.sock; check if the path is correct and if the daemon is running: dial unix /var/run/docker.sock: connect: no such file or directory
```

Konto SSH wymaga hasła do `sudo`. W trybie rootless brakuje systemowych `newuidmap` i `newgidmap`. Czas budowy, czas przebiegu kontenera, jego izolacja, trwałość ewidencji między kontenerami i zgodność bajtowa z A pozostają do pomiaru na silniku VPS.

## Powtórzenie z czystej kopii

Instrukcja jurora jest w [README](README.md). Z katalogu głównego czystej kopii gałęzi na VPS można powtórzyć cały odbiór jednym poleceniem po uruchomieniu silnika. Polecenie przygotuje identyczne wejścia do obu przebiegów, uruchomi `docker compose build cli`, wykona kolejne `docker compose run --rm` i porówna ścieżki, bajty oraz diagnostykę.

```sh
export PATH="$HOME/.local/bin:$PATH"
PROOF="$HOME/uzp-parallel/compose-proof"
RUN="$(mktemp -d "$PROOF/full.XXXXXX")"
"$PROOF/venv/bin/python" -m delivery.compose.verify "$RUN/run" \
  --dataset "$HOME/uzp-baseline-a/data/uzp" --tessdata "$PROOF/tessdata"
```

Flaga `--mode native` odtwarza wykonany przebieg bez Docker Engine. Testy regresji uruchomiono przez `python -m unittest discover -s evaluation -p 'test_*.py'` w tym samym środowisku. Prywatne logi są w `~/uzp-parallel/compose-proof/rehearsal.OhlpOd/`.
