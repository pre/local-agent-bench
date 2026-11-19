#!/usr/bin/env bash
#
# Archive the application logs of one log directory.
#
# Usage: rotate-logs.sh LOG_DIR ARCHIVE_DIR
#
# For each non-empty *.log file directly in LOG_DIR:
#   1. compress it to ARCHIVE_DIR/<name>-<stamp>.log.gz
#   2. write the SHA-256 of the archive to ARCHIVE_DIR/<name>-<stamp>.log.gz.sha256
#   3. truncate the log file (the services keep their file handles open)
#   4. keep only the KEEP newest archives of that log, remove the older ones
#
# A log that cannot be archived is left as it is. The script then continues
# with the other logs and exits with status 1 at the end.
#
# Environment:
#   KEEP   number of archives to keep for each log (default 14)
#   STAMP  time stamp in the archive name (default: current UTC time)

set -euo pipefail

usage() {
    echo "usage: $0 LOG_DIR ARCHIVE_DIR" >&2
    exit 2
}

[ $# -eq 2 ] || usage
LOG_DIR=$1
ARCHIVE_DIR=$2
KEEP=${KEEP:-14}
STAMP=${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}

log() {
    echo "$(date -u +%FT%TZ) rotate-logs: $*"
}

[ -d "$LOG_DIR" ] || { echo "rotate-logs: $LOG_DIR is not a directory" >&2; exit 1; }
mkdir -p "$ARCHIVE_DIR"

archive_log() {
    local file=$1 archive=$2
    gzip -c "$file" >"$archive" || return 1
    sha256sum "$archive" | awk '{print $1}' >"$archive.sha256" || return 1
}

prune_archives() {
    local name=$1 old
    find "$ARCHIVE_DIR" -maxdepth 1 -type f -name "$name-*.log.gz" -printf '%T@ %p\0' |
        sort -z -n -r |
        tail -z -n +$((KEEP + 1)) |
        while IFS= read -r -d '' old; do
            old=${old#* }
            rm -f -- "$old" "$old.sha256"
            log "removed old archive $old"
        done
}

rotated=0
failed=0
shopt -s nullglob
for file in "$LOG_DIR"/*.log; do
    if [ ! -f "$file" ] || [ ! -s "$file" ]; then
        continue
    fi
    name=$(basename "$file" .log)
    archive=$ARCHIVE_DIR/$name-$STAMP.log.gz

    if ! archive_log "$file" "$archive"; then
        rm -f -- "$archive" "$archive.sha256"
        echo "rotate-logs: cannot archive $file, the log is not truncated" >&2
        failed=$((failed + 1))
        continue
    fi
    : >"$file"
    log "archived $file to $archive"
    rotated=$((rotated + 1))

    prune_archives "$name"
done

log "done, $rotated file(s) rotated, $failed failed"
[ "$failed" -eq 0 ]
