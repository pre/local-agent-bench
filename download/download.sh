#!/bin/sh
# Download the GGUF files of models in download/models.tsv, one model after the other.
# Runs in an Alpine container (see "just download-model"):
#   /run/models.tsv   the data file (read-only)
#   /models/<model>/  the directory of each model (writable)
#   /run/host-ca.crt  the CA bundle of the host (TLS proxy)
#
# The URL has the pinned revision, not "main". aria2 writes FILE.part with
# 16 connections for each file, and the script renames it when aria2 completes
# the file. A second run continues the .part files. RATE is the limit for all
# connections together (aria2 unit: M = MiB/s).
#
# After the download the script checks each file with SHA-256 at low CPU and
# I/O priority. A file that does not match is downloaded again once.
set -u
RATE=${RATE:-28M}
TSV=/run/models.tsv

rows() { awk -F'\t' -v m="$1" '$1 == m' "$TSV"; }

write_metadata() {
  dir=/models/$1
  rows "$1" | awk -F'\t' '{printf "%s  %s\t%s\n", $7, $5, $6}' > "$dir/expected-sha256.tsv"
  rows "$1" | awk -F'\t' 'NR == 1 {printf "repo: %s\nrepo sha: %s  lastModified: %s\n", $2, $3, $4}' > "$dir/source.txt"
}

fetch() {
  dir=/models/$1
  : > /tmp/input.txt
  rows "$1" | while IFS="$(printf '\t')" read -r _ repo rev _ path _ _; do
    [ -f "$dir/$path" ] && { echo "have $1/$path"; continue; }
    printf '%s\n  out=%s.part\n' "https://huggingface.co/$repo/resolve/$rev/$path" "$path" >> /tmp/input.txt
  done
  [ -s /tmp/input.txt ] || return 0
  aria2c --input-file=/tmp/input.txt --dir="$dir" --continue=true \
    --max-concurrent-downloads=4 --max-connection-per-server=16 --split=16 --min-split-size=64M \
    --max-overall-download-limit="$RATE" \
    --file-allocation=none --auto-file-renaming=false \
    --max-tries=0 --retry-wait=10 --timeout=60 --connect-timeout=30 \
    --ca-certificate=/run/host-ca.crt \
    --console-log-level=warn --summary-interval=300
  rc=0
  for path in $(rows "$1" | cut -f5); do
    if [ -f "$dir/$path.part" ] && [ ! -f "$dir/$path.part.aria2" ]; then
      mv "$dir/$path.part" "$dir/$path" && echo "done $1/$path"
    fi
    [ -f "$dir/$path" ] || rc=1
  done
  return "$rc"
}

# Print the paths that do not match their SHA-256.
mismatches() {
  cd "/models/$1" || return
  cut -f1 expected-sha256.tsv | ionice -c 3 nice -n 19 sha256sum -c - 2>/dev/null | sed -n 's/: FAILED.*$//p'
  cd /
}

apk add --no-cache aria2 >/dev/null || exit 1

status=0
for model in "$@"; do
  [ -n "$(rows "$model")" ] || { echo "FAILED $model: not in $TSV"; status=1; continue; }
  write_metadata "$model"
  echo "$(date -u +%FT%TZ) start $model"
  if ! fetch "$model"; then
    echo "FAILED $model: download not complete, run again to continue"; status=1; continue
  fi
  echo "$(date -u +%FT%TZ) downloaded $model"
  bad=$(mismatches "$model")
  if [ -n "$bad" ]; then
    echo "SHA-256 mismatch, download again once: $bad"
    for path in $bad; do rm -f "/models/$model/$path"; done
    fetch "$model" && bad=$(mismatches "$model")
  fi
  if [ -n "$bad" ]; then
    echo "FAILED $model: SHA-256 mismatch: $bad"; status=1
  else
    echo "$(date -u +%FT%TZ) VERIFIED $model"
  fi
done
[ "$status" = 0 ] && echo "ALL DONE" || echo "FAILED: see the lines above"
exit "$status"
