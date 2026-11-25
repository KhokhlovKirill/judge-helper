#!/bin/sh
set -eu
umask 077
dir=$1
mkdir -p "$dir"
file="$dir/$(date -u +%Y%m%dT%H%M%SZ).dump"
pg_dump -Fc -f "$file.tmp"
pg_restore --list "$file.tmp" >/dev/null
mv "$file.tmp" "$file"
