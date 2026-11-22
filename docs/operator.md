# Panel operatora w obrazie jurora

Użyj obrazu `odwolania2json-jury:final-20261122` przygotowanego dla tej samej rewizji co [próba CLI](../RUN.md). Obraz zawiera Python 3.13 i polski OCR. Na hoście wystarczy Docker. Weryfikację pełnego SHA i ID obrazu opisuje [RUN.md](../RUN.md#przygotowanie-obrazu-przed-oceną).

## Uruchomienie pokazu

Na hoście oceny w powłoce administratora wykonaj:

```sh
umask 077
PANEL_RUN="$(mktemp -d)"
docker run --rm --pull=never --read-only \
  --user=0:0 --cap-drop=ALL --security-opt=no-new-privileges \
  --env OMP_THREAD_LIMIT=1 --publish 127.0.0.1:8765:8765 \
  --mount "type=bind,source=$PANEL_RUN,target=/work/demo" \
  --entrypoint python odwolania2json-jury:final-20261122 \
  -m operator_panel --demo-workspace /work/demo/przebiegi --ocr-data /opt/tessdata \
  --bind 0.0.0.0 --port 8765
```

Panel nasłuchuje na interfejsach kontenera, a Docker udostępnia port wyłącznie pod `127.0.0.1` hosta. Panel sprawdza adres `Host` i pochodzenie żądań zapisu. Polecenie montuje własny katalog pokazu. Domyślne polecenie obrazu nadal uruchamia partię z `RUN.md`.

Na komputerze z przeglądarką otwórz tunel, podając login i adres hosta oceny zamiast `LOGIN@HOST`:

```sh
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8765:127.0.0.1:8765 LOGIN@HOST
```

Otwórz `http://127.0.0.1:8765`. Przy przeglądarce działającej na hoście Dockera możesz użyć tego adresu bezpośrednio.

## Własny PDF, źródło i decyzja

Wybierz **Wgraj własny PDF**, a następnie **Przetwórz PDF**. Panel przyjmuje jeden plik do 32 MiB w każdej próbie. Możesz wgrać syntetyczny skan `delivery/compose/skan-syntetyczny.pdf` z kopii projektu. Każdy upload zapisuje osobny przebieg w `$PANEL_RUN/przebiegi/<id>/`, z własnymi katalogami `input/`, `output/` i `diagnostics/`.

Otwórz przetworzony `dokument.pdf`, wskaż pole i otwórz fizyczną stronę z dowodem. W skanie demonstracyjnym kwota 123,45 pochodzi ze strony 1. Porównaj wynik ze stroną i zapisz akceptację lub korektę. Decyzja trafia do `diagnostics/run.decisions.sqlite3`. Surowy JSON nadal zawiera wynik ekstrakcji. Zakończ serwer przez Ctrl+C.

[CLI jurora](../RUN.md) · [Próba dodania klasy](../README.md#reguły-i-rozszerzanie)
