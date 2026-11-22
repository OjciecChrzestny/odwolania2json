# Odwołania2JSON przez Docker Compose

Wymagany jest uruchomiony Docker Engine obsługujący kontenery Linux i Docker Compose v2. Compose uruchamia lokalny obraz `odwolania2json-jury:final-20261122`. Przed użyciem wczytaj obraz przygotowany z zatwierdzonego SHA zgodnie z [RUN.md](../../RUN.md#przygotowanie-obrazu-przed-oceną). Przetwarzanie działa lokalnie na CPU. Usługa uruchamia publiczne CLI z włączonym polskim OCR i z trybem sieci `none`. [Dokumentacja Docker Compose](https://docs.docker.com/reference/compose-file/services/#network_mode)

## Uprawnienia na Linuxie

Domyślne Compose i `RUN.md` używają UID/GID `0:0` w kontenerze. W trybie rootless odpowiada to użytkownikowi demona na hoście. W samodzielnym przebiegu na zwykłym Docker Engine możesz ustawić `ODW_UID` i `ODW_GID` na identyfikatory właściciela własnych katalogów.

## Domyślne katalogi

Domyślne Compose używa tych samych `input/`, `output/`, `.output.odwolania2json/` i `diagnostics/` co [RUN.md](../../RUN.md). W świeżej kopii repozytorium na Linuxie utwórz katalogi, a do `input/` wstaw swoje PDF-y, również w podkatalogach.

```sh
mkdir -p input output diagnostics .output.odwolania2json
docker compose run --rm cli
find output -type f
```

Na Windows z Docker Desktop w trybie Linux, w PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path input,output,diagnostics,.output.odwolania2json | Out-Null
# Wstaw PDF-y do input.
docker compose run --rm cli
Get-ChildItem output -Recurse -File
```

Wejście `input/sprawa/pismo.pdf` daje `output/sprawa/pismo.json`. Dokument obcy daje plik 0 B. W `diagnostics/last-run.json` znajdziesz status każdego PDF-u, listę stron użytych przez OCR i pochodzenie wydobytych pól. Kod 1 oznacza co najmniej jeden błąd odczytu. Kod 2 oznacza błąd konfiguracji lub operacji na drzewie.

## Własne katalogi jurora

Użyj trzech odrębnych katalogów na hoście. Compose składa ścieżkę wyjścia z katalogu nadrzędnego (`ODW_OUTPUT_PARENT`) i nazwy katalogu (`ODW_OUTPUT_NAME`). Ewidencję zapisuje obok wyjścia w `.<nazwa>.odwolania2json/`, zgodnie z natywnym CLI. Zostaw ewidencję na miejscu między uruchomieniami. Gdy usuniesz wejściowy PDF i ponownie uruchomisz usługę, CLI usunie odpowiadający mu poprzedni wynik. Plik ręcznie dodany do drzewa wyników pozostanie na miejscu.

Linux, po przygotowaniu obrazu:

```sh
export ODW_INPUT_DIR="$HOME/PDF jurora"
OUT="$HOME/JSON jurora"
export ODW_OUTPUT_PARENT="$(dirname "$OUT")" ODW_OUTPUT_NAME="$(basename "$OUT")"
export ODW_DIAGNOSTICS_DIR="$HOME/Diagnostyka jurora"
mkdir -p "$ODW_INPUT_DIR" "$OUT" "$ODW_OUTPUT_PARENT/.${ODW_OUTPUT_NAME}.odwolania2json" "$ODW_DIAGNOSTICS_DIR"
# Wstaw PDF-y do "$ODW_INPUT_DIR".
docker compose run --rm cli
find "$OUT" -type f
```

Windows, po przygotowaniu obrazu:

```powershell
$env:ODW_INPUT_DIR = Join-Path $HOME 'PDF jurora'
$outDir = Join-Path $HOME 'JSON jurora'
$env:ODW_OUTPUT_PARENT = Split-Path -Parent $outDir
$env:ODW_OUTPUT_NAME = Split-Path -Leaf $outDir
$env:ODW_DIAGNOSTICS_DIR = Join-Path $HOME 'Diagnostyka jurora'
New-Item -ItemType Directory -Force -Path @(
    $env:ODW_INPUT_DIR
    $outDir
    (Join-Path $env:ODW_OUTPUT_PARENT ".${env:ODW_OUTPUT_NAME}.odwolania2json")
    $env:ODW_DIAGNOSTICS_DIR
) | Out-Null
# Wstaw PDF-y do $env:ODW_INPUT_DIR.
docker compose run --rm cli
Get-ChildItem -LiteralPath $outDir -Recurse -File
```

W nowej powłoce usługa wraca do domyślnych ścieżek. Aby zacząć nowy przebieg, wybierz nowe wyjście i katalog diagnostyki.

## Własna budowa do prób

Do sprawdzenia lokalnej zmiany użyj osobnego tagu. Polecenie Compose skorzysta z niego dzięki `ODW_JURY_IMAGE`.

```sh
export ODW_JURY_IMAGE=odwolania2json-jury:lokalna-proba
docker build --target jury --tag "$ODW_JURY_IMAGE" .
```

## Porównanie z natywnym CLI

Z katalogu głównego czystej kopii na Linuxie z Dockerem i Pythonem 3.13+ przygotuj natywne środowisko i `pol.traineddata` według [głównego README](../../README.md#opcjonalny-ocr). `UZP_DATA` to ścieżka do kopii danych UZP na rewizji `de135d20811caf630f3e94dc655ba5eebd9a6710`. `TESSDATA` to bezwzględna ścieżka do katalogu z polskim plikiem językowym. Po aktywacji środowiska wykonaj jedno polecenie:

```sh
python -m delivery.compose.verify "$HOME/odbior-compose" --dataset "$UZP_DATA" --tessdata "$TESSDATA"
```

Sprawdzenie wymaga nowej ścieżki przebiegu i tworzy domyślne katalogi w świeżej kopii projektu. Używa wyłącznie czterech PDF-ów rozwojowych, kopii jednego z nich oraz syntetycznego skanu. W trybie z dwoma hostami uruchom to samo polecenie z `--mode native`, przekaż prywatnie katalog przebiegu i użyj na hoście Docker z tym samym SHA polecenia `python -m delivery.compose.verify ŚCIEŻKA_PRZEBIEGU --mode compose`.
