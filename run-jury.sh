#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
mode=${1:-batch}
image=odwolania2json-jury:auto-20261122
umask 077

# Ocena i panel dzielą jeden trwały licznik. Bez klucza ten sam obraz działa lokalnie.
if [ -f "$root/.env" ] && [ ! -L "$root/.env" ]; then
    mkdir -p "$root/.llm-jury"
    set -- --network=bridge \
        --mount "type=bind,source=$root/.env,target=/run/odwolania2json/scaleway.env,readonly" \
        --mount "type=bind,source=$root/.llm-jury,target=/work/llm"
else
    set -- --network=none
    if [ "$mode" = panel ]; then set -- --network=bridge; fi
fi
set -- --pull=never --read-only --user=0:0 --cap-drop=ALL --cap-add=DAC_OVERRIDE \
    --security-opt=no-new-privileges --env OMP_THREAD_LIMIT=1 "$@"
case "$mode" in
    batch)
        test -d "$root/input"
        test -d "$root/output"
        mkdir -p "$root/.output.odwolania2json" "$root/diagnostics"
        exec docker run --rm "$@" \
            --mount "type=bind,source=$root/input,target=/work/input,readonly" \
            --mount "type=bind,source=$root/output,target=/work/output" \
            --mount "type=bind,source=$root/.output.odwolania2json,target=/work/.output.odwolania2json" \
            --mount "type=bind,source=$root/diagnostics,target=/work/diagnostics" \
            "$image" --ocr-max-pages 6
        ;;
    panel)
        mkdir -p "$root/panel-demo"
        exec docker run --detach --name odwolania2json-panel-auto --restart=unless-stopped "$@" \
            --publish 127.0.0.1:8765:8765 \
            --mount "type=bind,source=$root/panel-demo,target=/work/demo" \
            --entrypoint python "$image" -m operator_panel --demo-workspace /work/demo/przebiegi \
            --ocr-data /opt/tessdata --bind 0.0.0.0 --port 8765
        ;;
    *) echo "Użycie: ./run-jury.sh [batch|panel]" >&2; exit 2 ;;
esac
