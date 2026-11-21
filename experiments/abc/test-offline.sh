#!/bin/sh
# Próby na tej samej wersji pakietu co publiczne CLI.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
python=$("${PYTHON:-python3}" -c 'import os, sys; print(os.path.abspath(sys.executable))')
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
cd "$repo"
mkdir "$scratch/tmp"
unset OVH_AI_ENDPOINTS_ACCESS_TOKEN SCALEWAY_SECRET_KEY SCW_SECRET_KEY PYTHONPATH UZP_DATA
export TMPDIR="$scratch/tmp" PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1

if [ "${LANDLOCK:-0}" = 1 ]; then
    prefix=$("$python" -c 'import sys; print(sys.prefix)')
    base=$("$python" -c 'import sys; print(sys.base_prefix)')
    cc -std=c11 -O2 -Wall -Wextra -Werror evaluation/restrict_linux.c -o "$scratch/restrict-linux"
    set -- "$scratch/restrict-linux" -r /usr -r /etc/ld.so.cache -r /dev/urandom -r /dev/null \
        -r "$prefix" -r "$base" -r "$PWD" -w "$TMPDIR" -- "$python"
    "$@" -c '
import errno, socket
with socket.socket() as sock:
    try:
        sock.connect(("127.0.0.1", 9))
    except PermissionError as error:
        assert error.errno in {errno.EACCES, errno.EPERM}
    else:
        raise SystemExit("TCP dostępne")
print("Landlock: połączenie TCP zablokowane")
'
else
    set -- "$python"
fi

"$@" -m unittest -v experiments.abc.test_offline
"$@" -m unittest discover -s evaluation -p "test_*.py"
