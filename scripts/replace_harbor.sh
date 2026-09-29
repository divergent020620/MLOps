#!/bin/bash
# usage: bash script/replace_harbor.sh <src_ip> <dst_ip> [dir]
# example: bash replace_harbor.sh 192.168.11.12 10.240.125.39 /path/to/dir

set -e

SRC="${1:?source ip required}"
DST="${2:?dest ip required}"
DIR="${3:-.}"
SELF="$(realpath "$0")"

find "$DIR" -type f | while read -r f; do
    f_real="$(realpath "$f")"
    [ "$f_real" = "$SELF" ] && continue
    grep -q "$SRC" "$f" 2>/dev/null || continue
    sed -i "s|$SRC|$DST|g" "$f"
    echo "[OK] $f"
done

echo "Done."
