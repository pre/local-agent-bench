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
# Environment:
#   KEEP   number of archives to keep for each log (default 14)
#   STAMP  time stamp in the archive name (default: current UTC time)

set -eu

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

rotated=0
for file in $(find $LOG_DIR -maxdepth 1 -type f -name '*.log'); do
    if [ ! -s $file ]; then
        continue
    fi
    name=$(basename $file .log)
    archive=$ARCHIVE_DIR/$name-$STAMP.log.gz

    gzip -c $file | tee $archive | sha256sum | awk '{print $1}' > $archive.sha256
    : > $file
    log "archived $file to $archive"
    rotated=$((rotated + 1))

    ls -1t $ARCHIVE_DIR/$name-*.log.gz | tail -n +$((KEEP + 1)) | while read old; do
        rm -f $old $old.sha256
        log "removed old archive $old"
    done
done

log "done, $rotated file(s) rotated"
