#!/usr/bin/env bash
# Ekstrakcja z katalogu zawierającego wyłącznie pakiet z mierzonego commita.
set -euo pipefail
if [[ $# != 3 ]]; then
    printf 'Użycie: %s KATALOG_NARZĘDZI KATALOG_PRODUKTU KATALOG_PRZEBIEGU\n' "$0" >&2
    exit 2
fi
tools=$(realpath "$1")
product=$(realpath "$2")
run=$(realpath "$3")
cd "$product"
mkdir -p "$run/output" "$run/diagnostics" "$run/.output.odwolania2json"
unset UZP_DATA PYTHONPATH
export PYTHONDONTWRITEBYTECODE=1 OMP_THREAD_LIMIT=1 LC_ALL=C.UTF-8
/usr/bin/time -v -o "$run/time.txt" \
    "$tools/restrict-linux" \
    -r /usr -r /etc/ld.so.cache -r /dev/null -r /dev/urandom \
    -r "$tools/venv" -r "$tools/python" -r "$tools/tessdata" -r "$product" \
    -r "$run/input" -w "$run/output" -w "$run/diagnostics" -w "$run/.output.odwolania2json" -- \
    "$tools/venv/bin/python" -m odwolania2json \
    --input "$run/input" --output "$run/output" \
    --diagnostics "$run/diagnostics/extraction.json" --ocr-data "$tools/tessdata"
