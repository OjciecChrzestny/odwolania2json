# Panel operatora na VPS

Panel z katalogu `operator_panel/` działa na Pythonie 3.13 i nasłuchuje na `127.0.0.1`. Użyj czystej kopii wydania zawierającej panel, ekstraktor oraz ich zależności. Instalację wykonaj wcześniej. Ekstrakcja w tej próbie używa lokalnego OCR.

## Przygotowanie środowiska

Z katalogu głównego repozytorium na VPS:

```sh
umask 077
PANEL_RUN="$(mktemp -d)"
python3.13 -m venv "$PANEL_RUN/venv"
PY="$PANEL_RUN/venv/bin/python"
"$PY" -m pip install --only-binary=:all: -r operator_panel/requirements.txt -r requirements-ocr.txt
TESSDATA="$PANEL_RUN/tessdata"
mkdir "$TESSDATA"
curl -fsSL https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/pol.traineddata \
  -o "$TESSDATA/pol.traineddata"
printf '%s  %s\n' c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2 \
  "$TESSDATA/pol.traineddata" | sha256sum -c -
```

## Własny PDF w przeglądarce

W tej samej powłoce uruchom tryb demonstracyjny:

```sh
OMP_THREAD_LIMIT=1 "$PY" -m operator_panel --demo-workspace "$PANEL_RUN/przebiegi" \
  --ocr-data "$TESSDATA" --port 8765
```

Po otwarciu tunelu wybierz **Wgraj własny PDF**, a następnie **Przetwórz PDF**. Panel obsługuje jeden plik do 32 MiB na próbę. Każdy upload uruchamia lokalne CLI z polskim OCR i zapisuje osobny przebieg w `$PANEL_RUN/przebiegi/<id>/`, z własnymi katalogami `input/`, `output/` i `diagnostics/`. Panel otwiera wynik i jego dowody po przetworzeniu. Do próby można wgrać syntetyczny plik `delivery/compose/skan-syntetyczny.pdf`.

## Tunel i decyzja

Na komputerze oceniającego, w osobnym terminalu, otwórz tunel do hosta, na którym działa panel. Alias `hacknation` oznacza deweloperski VPS.

```sh
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8765:127.0.0.1:8765 hacknation
```

Otwórz `http://127.0.0.1:8765`. Wybierz przetworzony `dokument.pdf`, wskaż pole i otwórz fizyczną stronę z dowodem. Dla syntetycznego skanu można sprawdzić kwotę 123,45 na stronie 1. Porównaj wynik ze stroną, a potem zapisz akceptację lub korektę. Decyzja trafia do `diagnostics/run.decisions.sqlite3` obok raportu. Surowy JSON nadal zawiera wynik ekstrakcji.

[CLI jurora](../RUN.md) · [Próba dodania klasy](../demo/rozszerzalnosc/README.md)
