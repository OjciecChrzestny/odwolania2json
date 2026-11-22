# Uruchomienie oceny na VM

Z katalogu `/opt/solution` w powłoce z uprawnieniami administratora wykonaj cały blok. Katalogi `input/` i `output/` przygotowuje jury.

```sh
test -d "$PWD/input" &&
test -d "$PWD/output" &&
mkdir -p "$PWD/.jury/state" "$PWD/.jury/diagnostics" &&
docker run --rm --pull=never --network=none --read-only \
  --user=0:0 --cap-drop=ALL --cap-add=DAC_OVERRIDE \
  --security-opt=no-new-privileges \
  --env OMP_THREAD_LIMIT=1 \
  --mount "type=bind,source=$PWD/input,target=/work/input,readonly" \
  --mount "type=bind,source=$PWD/output,target=/work/output" \
  --mount "type=bind,source=$PWD/.jury/state,target=/work/.output.odwolania2json" \
  --mount "type=bind,source=$PWD/.jury/diagnostics,target=/work/diagnostics" \
  odwolania2json-jury:6eb211c39c6c
```

CLI odczytuje PDF-y rekurencyjnie. `input/sprawa/pismo.pdf` daje `output/sprawa/pismo.json`. Dokument obcy daje plik o rozmiarze 0 B. Błąd odczytu pomija wynik danego PDF-u, zapisuje `read_error` i kończy komendę kodem 1 po przetworzeniu pozostałych plików. Kod 2 oznacza błąd konfiguracji lub zapisu. Diagnostyka jest w `.jury/diagnostics/last-run.json`, a ewidencja w `.jury/state/`. Można wyczyścić zawartość `input/` i `output/` między próbami, zachowując same katalogi.

## Przygotowanie obrazu przed oceną

W magazynie Dockera używanym przez administratora VM musi być lokalny obraz `odwolania2json-jury:6eb211c39c6c`. Przed oceną zbuduj go z katalogu projektu poleceniem `docker build --target jury --tag odwolania2json-jury:6eb211c39c6c .` albo wczytaj gotowe archiwum przez `docker image load --input ŚCIEŻKA_ARCHIWUM`. Obraz zawiera Python 3.13, lokalne reguły i polski OCR. Przetwarzanie działa bez usług zewnętrznych i kluczy API. Kontener kończy działanie po partii.
