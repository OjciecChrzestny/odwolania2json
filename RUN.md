# Uruchomienie oceny na VM

Z katalogu `/opt/solution` w powłoce z uprawnieniami administratora wykonaj cały blok. Katalogi `input/` i `output/` przygotowuje jury.

```sh
test -d "$PWD/input" &&
test -d "$PWD/output" &&
mkdir -p "$PWD/.output.odwolania2json" "$PWD/diagnostics" &&
docker run --rm --pull=never --network=none --read-only \
  --user=0:0 --cap-drop=ALL --cap-add=DAC_OVERRIDE \
  --security-opt=no-new-privileges \
  --env OMP_THREAD_LIMIT=1 \
  --mount "type=bind,source=$PWD/input,target=/work/input,readonly" \
  --mount "type=bind,source=$PWD/output,target=/work/output" \
  --mount "type=bind,source=$PWD/.output.odwolania2json,target=/work/.output.odwolania2json" \
  --mount "type=bind,source=$PWD/diagnostics,target=/work/diagnostics" \
  odwolania2json-jury:final-20261122
```

CLI odczytuje PDF-y rekurencyjnie. `input/sprawa/pismo.pdf` daje `output/sprawa/pismo.json`. Dokument obcy daje plik o rozmiarze 0 B. Błąd odczytu pomija wynik danego PDF-u, zapisuje `read_error` i kończy komendę kodem 1 po przetworzeniu pozostałych plików. Kod 2 oznacza błąd konfiguracji lub zapisu. Diagnostyka jest w `diagnostics/last-run.json`, a ewidencja w `.output.odwolania2json/`. Domyślne Compose używa tych samych katalogów i ewidencji. Przy zmianie sposobu uruchomienia pozostaw `output/` oraz `.output.odwolania2json/` na miejscu.

Jeśli dotychczasowe wyniki powstały ze starszego polecenia RUN i ich ewidencja jest w `.jury/state/`, zatrzymaj wszystkie przebiegi. Jeżeli `.output.odwolania2json/` jeszcze nie istnieje, przenieś całą ewidencję poleceniem `mv .jury/state .output.odwolania2json` w katalogu rozwiązania. Jeśli istnieją obie ewidencje, zabezpiecz obie i ustal, która odpowiada bieżącemu `output/`, przed wznowieniem pracy.

## Przygotowanie obrazu przed oceną

Po zamrożeniu wydania ustaw `REV` na pełny SHA zatwierdzonego kodu. Koordynator buduje obraz z archiwum tej rewizji, z katalogu repozytorium i w magazynie Dockera używanym do oceny.

```bash
(
  set -eu
  : "${REV:?Ustaw REV na pełny SHA zamrożonego wydania}"
  test "${#REV}" -eq 40
  test "$(git rev-parse --verify "$REV^{commit}")" = "$REV"
  IMAGE=odwolania2json-jury:final-20261122
  BUILD="$(mktemp -d)"
  git archive --format=tar "$REV" > "$BUILD/kod.tar"
  test "$(git get-tar-commit-id < "$BUILD/kod.tar")" = "$REV"
  mkdir "$BUILD/kod"
  tar --same-permissions -xf "$BUILD/kod.tar" -C "$BUILD/kod"
  docker build --target jury --label "org.opencontainers.image.revision=$REV" \
    --tag "$IMAGE" "$BUILD/kod"
  docker image inspect "$IMAGE" --format '{{.Id}} {{index .Config.Labels "org.opencontainers.image.revision"}}'
)
```

Przy przenoszeniu obrazu sprawdź sumę archiwum i wczytaj je przez `docker image load --input ŚCIEŻKA_ARCHIWUM`. Na serwerze oceny zapisz pełny SHA źródeł z etykiety i `Image ID` zwrócony przez ostatnie polecenie. Przed restartem serwera przygotuj pliki projektu, uruchomiony demon Dockera oraz lokalny obraz. Po restarcie sprawdź ten sam tag, ID i etykietę w magazynie administratora. Próbę przed przekazaniem wykonaj na własnych przykładach. Kontener oceny korzysta z Pythona 3.13 i polskiego OCR, działa offline i kończy pracę po partii.
