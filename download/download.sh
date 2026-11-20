#!/bin/sh
# Download the GGUF files of models in download/models.tsv, one model after the other.
# Runs in an Alpine container (see "just download-model"):
#   /run/models.tsv   the data file (read-only)
#   /models/<model>/  the directory of each model (writable)
#   /run/host-ca.crt  the CA bundle of the host (TLS proxy)
# TSV and MODELS change the first two paths.
#
# The URL has the pinned revision, not "main". aria2 writes FILE.part with
# 16 connections for each file. A second run continues the .part files. RATE is
# the limit for all connections together (aria2 unit: M = MiB/s).
#
# When a .part file is complete, the script checks it with SHA-256 at low CPU and
# I/O priority. Only a file that matches gets its final name, so the server cannot
# load a file that is not verified. A file that does not match becomes FILE.bad and
# is downloaded again once. The next download of the file removes FILE.bad.
#
# aria2 stops when the TLS proxy breaks connections, so the script starts it
# again (ATTEMPTS times, RETRY_WAIT seconds apart). Each model directory gets download.log with the status
# lines, because "podman logs" can lose lines of a long log.
#
# download.sh --verify MODEL...  checks the files with their final names against
# the data file, on the host or in the container. It downloads nothing. The exit
# code is 1 when a file is missing or does not match.
set -u
RATE=${RATE:-28M}
ATTEMPTS=${ATTEMPTS:-5}
RETRY_WAIT=${RETRY_WAIT:-60}
TSV=${TSV:-/run/models.tsv}
MODELS=${MODELS:-/models}

rows() { awk -F'\t' -v m="$1" '$1 == m' "$TSV"; }

# A status line to stdout and to download.log of the model.
note() { line="$(date -u +%FT%TZ) $2"; echo "$line"; echo "$line" >> "$MODELS/$1/download.log"; }

sha256() { ionice -c 3 nice -n 19 sha256sum -c -; }

# aria2 removes the control file FILE.part.aria2 when the file is complete.
finished() { [ -f "$1" ] && [ ! -f "$1.aria2" ]; }

write_metadata() {
  dir=$MODELS/$1
  rows "$1" | awk -F'\t' '{printf "%s  %s\t%s\n", $7, $5, $6}' > "$dir/expected-sha256.tsv"
  rows "$1" | awk -F'\t' 'NR == 1 {printf "repo: %s\nrepo sha: %s  lastModified: %s\n", $2, $3, $4}' > "$dir/source.txt"
}

# Download each file that has no final name and no complete .part file.
# Return 1 when a file is still not complete.
fetch() {
  dir=$MODELS/$1
  input=$(mktemp)
  rows "$1" | while IFS="$(printf '\t')" read -r _ repo rev _ path _ _; do
    [ -f "$dir/$path" ] && { echo "have $1/$path"; continue; }
    finished "$dir/$path.part" && continue
    rm -f "$dir/$path.bad"
    printf '%s\n  out=%s.part\n' "https://huggingface.co/$repo/resolve/$rev/$path" "$path" >> "$input"
  done
  attempt=1
  while [ -s "$input" ] && ! aria2c --input-file="$input" --dir="$dir" --continue=true \
    --max-concurrent-downloads=4 --max-connection-per-server=16 --split=16 --min-split-size=64M \
    --max-overall-download-limit="$RATE" \
    --file-allocation=none --auto-file-renaming=false \
    --max-tries=0 --retry-wait=10 --timeout=60 --connect-timeout=30 \
    --ca-certificate=/run/host-ca.crt \
    --console-log-level=warn --summary-interval=300; do
    [ "$attempt" -ge "$ATTEMPTS" ] && break
    note "$1" "aria2 attempt $attempt failed, start again in $RETRY_WAIT s"
    attempt=$((attempt + 1))
    sleep "$RETRY_WAIT"
  done
  rm -f "$input"
  rc=0
  for path in $(rows "$1" | cut -f5); do
    [ -f "$dir/$path" ] || finished "$dir/$path.part" || rc=1
  done
  return "$rc"
}

# Give each complete .part file its final name when its SHA-256 matches, else the
# name FILE.bad. Return 1 when a file does not match.
promote() {
  dir=$MODELS/$1
  rc=0
  for row in $(rows "$1" | awk -F'\t' '{print $5 "|" $7}'); do
    path=${row%|*}
    finished "$dir/$path.part" || continue
    if echo "${row#*|}  $dir/$path.part" | sha256 >/dev/null; then
      mv "$dir/$path.part" "$dir/$path" && echo "verified $1/$path"
    else
      mv "$dir/$path.part" "$dir/$path.bad" && echo "SHA-256 mismatch: $1/$path, kept as $path.bad"
      rc=1
    fi
  done
  return "$rc"
}

# Check the files with their final names. sha256sum is the last command of the
# pipe, so its exit code is the exit code of the pipe. Each file must give one OK line.
verify() {
  out=$(rows "$1" | awk -F'\t' '{printf "%s  %s\n", $7, $5}' | (cd "$MODELS/$1" && sha256))
  rc=$?
  echo "$out"
  [ "$rc" = 0 ] && [ "$(echo "$out" | grep -c ': OK$')" -eq "$(rows "$1" | wc -l)" ]
}

download() {
  write_metadata "$1"
  note "$1" "start $1"
  if ! fetch "$1"; then
    note "$1" "FAILED $1: download not complete, run again to continue"
    return 1
  fi
  note "$1" "downloaded $1"
  promote "$1" || { note "$1" "download again once: $1"; fetch "$1" && promote "$1"; }
  return 0
}

mode=download
[ "${1:-}" = --verify ] && { mode=verify; shift; }
[ "$mode" = verify ] || apk add --no-cache aria2 >/dev/null || exit 1

status=0
for model in "$@"; do
  if [ -z "$(rows "$model")" ]; then
    echo "FAILED $model: not in $TSV"; status=1
  elif [ "$mode" = download ] && ! download "$model"; then
    status=1
  elif verify "$model"; then
    note "$model" "VERIFIED $model"
  else
    note "$model" "FAILED $model: a file is missing or does not match its SHA-256"; status=1
  fi
done
[ "$status" = 0 ] && echo "ALL DONE" || echo "FAILED: see the lines above"
exit "$status"
