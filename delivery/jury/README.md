# Odwołania2JSON dla jurora

[Wyniki jakości i próba offline](docs/jakosc.md)

## Partia PDF-ów

Z katalogu rozpakowanej paczki wykonaj [polecenie z RUN.md](RUN.md). Używa ono przygotowanego lokalnie obrazu `odwolania2json-jury:final-20261122` z Pythonem 3.13 i polskim OCR. Na VM użyj istniejących `input/` i `output/`. We własnej kopii możesz utworzyć oba katalogi przez `mkdir -p input output`. Zagnieżdżony `input/sprawa/pismo.pdf` daje `output/sprawa/pismo.json`. Dokument obcy daje plik 0 B, a źródła pól są w `diagnostics/last-run.json`.

W tej samej kopii możesz wykonać partię przez Compose. Domyślna usługa używa tego samego obrazu, katalogów i ewidencji.

```sh
mkdir -p input output diagnostics .output.odwolania2json
docker compose run --rm --pull never -e OMP_THREAD_LIMIT=1 cli
```

## Panel z własnym PDF-em

[Uruchom panel na lokalnym porcie i wgraj PDF](docs/operator.md). Otwórz wskazaną stronę fizyczną i zapisz decyzję. Do sprawdzenia OCR możesz użyć [syntetycznego skanu](delivery/compose/skan-syntetyczny.pdf).

## Reguły i rozszerzanie

Pokaz dodaje [klasę zawiadomienia](demo/rozszerzalnosc/zawiadomienie.json) i [obiekt miejsca posiedzenia](demo/rozszerzalnosc/miejsce_posiedzenia.json) przez zmianę kopii konfiguracji. Na hoście wystarczą Docker i systemowy Python 3.12. Pierwsze polecenie generuje przykładowy PDF w kontenerze. Zamiast wygenerowanego pliku możesz przekazać własny PDF z nagłówkiem `ZAWIADOMIENIE`, sygnaturą i wierszami terminu, budynku oraz opcjonalnej sali.

```sh
DEMO="$PWD/demo/rozszerzalnosc"
WORK="$(mktemp -d)"
IMAGE=odwolania2json-jury:final-20261122
CLI_USER="$(id -u):$(id -g)"
# Dla Docker rootless ustaw CLI_USER=0:0.
docker run --rm --pull=never --network=none --read-only --user "$CLI_USER" \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --mount "type=bind,source=$DEMO,target=/app/demo,readonly" \
  --mount "type=bind,source=$WORK,target=/work/demo" \
  --entrypoint python "$IMAGE" -B -c \
  'import sys; from pathlib import Path; sys.path.insert(0, "/app/demo"); from obiekt import prepare_input; prepare_input(Path("/work/demo/wejscie"))'
python3 -S -B "$DEMO/obiekt.py" --image "$IMAGE" --user "$CLI_USER" \
  --work "$WORK/pokaz" --tylko-pdf --pdf "$WORK/wejscie/p01.pdf"
cat "$WORK/pokaz/juror-obiekt/output/p04.json"
```

Profil konkursowy daje 0 B. Dodana klasa zwraca sygnaturę i termin. Po dodaniu obiektu wynik zawiera budynek `Alfa` i salę `207`. W `$WORK/pokaz/roznica-obiektu.diff` widać zmianę samej konfiguracji. Powrót do profilu konkursowego odtwarza 0 B. Diagnostyka pokazu wskazuje źródła na stronie 2.

Zależności są przypięte w [requirements.txt](requirements.txt), [requirements-ocr.txt](requirements-ocr.txt) i [operator_panel/requirements.txt](operator_panel/requirements.txt). Licencje komponentów udostępniają [Python](https://docs.python.org/3.13/license.html), [pypdf](https://pypi.org/project/pypdf/6.21.4/), [pypdfium2 i PDFium](https://github.com/pypdfium2-team/pypdfium2/blob/5.15.2/README.md#licensing), [tesserocr](https://pypi.org/project/tesserocr/2.13.0/), [Tesseract](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE), [dane OCR](https://github.com/tesseract-ocr/tessdata_fast/blob/4.1.0/LICENSE) i [Pillow](https://pypi.org/project/pillow/13.0.0/).
