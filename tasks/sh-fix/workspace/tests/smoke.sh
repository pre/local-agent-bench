#!/usr/bin/env bash
# Smoke test: rotate one log in a scratch directory.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT

mkdir -p "$scratch/logs"
printf 'line 1\nline 2\n' > "$scratch/logs/app.log"
STAMP=20260101T000000Z "$here/../bin/rotate-logs.sh" "$scratch/logs" "$scratch/archive"

archive=$scratch/archive/app-20260101T000000Z.log.gz
[ "$(gzip -dc "$archive")" = "$(printf 'line 1\nline 2')" ]
[ "$(cat "$archive.sha256")" = "$(sha256sum "$archive" | awk '{print $1}')" ]
[ ! -s "$scratch/logs/app.log" ]
echo "smoke test passed"
