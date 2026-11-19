#!/usr/bin/env bash
# Hidden check of the sh-fix task: behavior of bin/rotate-logs.sh in scratch
# trees below /tmp, and shellcheck on the script.
# The test functions run through "check" from lib.sh.
# shellcheck disable=SC2329
set -u
VERIFY_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
. "$VERIFY_DIR/lib.sh"

SCRIPT=/work/bin/rotate-logs.sh
STAMP_NEW=20261118T021500Z

run_script() { # run_script LOG_DIR ARCHIVE_DIR (KEEP, STAMP and PATH come from the caller)
    STAMP=$STAMP_NEW timeout 30 bash "$SCRIPT" "$1" "$2"
}

# assert_archived LOG_FILE ARCHIVE_DIR EXPECTED_CONTENT
assert_archived() {
    local file=$1 archive_dir=$2 expected=$3 name archive
    name=$(basename "$file" .log)
    archive=$archive_dir/$name-$STAMP_NEW.log.gz
    [ -f "$archive" ] || { echo "missing archive: $archive"; return 1; }
    [ "$(gzip -dc "$archive")" = "$expected" ] || { echo "wrong content in $archive"; return 1; }
    [ -f "$archive.sha256" ] || { echo "missing checksum: $archive.sha256"; return 1; }
    [ "$(awk '{print $1; exit}' "$archive.sha256")" = "$(sha256sum "$archive" | awk '{print $1}')" ] ||
        { echo "wrong checksum in $archive.sha256"; return 1; }
    [ -f "$file" ] && [ ! -s "$file" ] || { echo "log not truncated: $file"; return 1; }
}

new_tree() {
    rm -rf "$1"
    mkdir -p "$1"
}

test_plain_paths() {
    local t=/tmp/rl-plain
    new_tree "$t"
    mkdir -p "$t"/logs
    printf 'GET /healthz 200\nGET /api/v1/nodes 200\n' >"$t"/logs/inventory-api.log
    printf 'worker started\n' >"$t"/logs/worker.log
    KEEP=14 run_script "$t"/logs "$t"/archive || { echo "exit status $?"; return 1; }
    assert_archived "$t"/logs/inventory-api.log "$t"/archive "$(printf 'GET /healthz 200\nGET /api/v1/nodes 200')" &&
        assert_archived "$t"/logs/worker.log "$t"/archive "worker started"
}

test_spaces_in_paths() {
    local t="/tmp/rl spaces" logs archive
    new_tree "$t"
    logs="$t/srv/logs/payment gateway"
    archive="$t/srv/archive/payment gateway"
    mkdir -p "$logs/old run"
    printf 'POST /charge 201\n' >"$logs/api.log"
    printf 'row 17: missing currency\nrow 18: missing currency\n' >"$logs/export errors.log"
    printf 'job * started\n' >"$logs/worker 2.log"
    : >"$logs/empty.log"
    printf 'keep me\n' >"$logs/notes.txt"
    printf 'nested\n' >"$logs/old run/nested.log"
    KEEP=3 run_script "$logs" "$archive" || { echo "exit status $?"; return 1; }
    assert_archived "$logs/api.log" "$archive" "POST /charge 201" &&
        assert_archived "$logs/export errors.log" "$archive" "$(printf 'row 17: missing currency\nrow 18: missing currency')" &&
        assert_archived "$logs/worker 2.log" "$archive" "job * started" || return 1
    [ ! -e "$archive/empty-$STAMP_NEW.log.gz" ] || { echo "empty log was archived"; return 1; }
    [ "$(cat "$logs/notes.txt")" = "keep me" ] || { echo "notes.txt changed"; return 1; }
    [ "$(cat "$logs/old run/nested.log")" = "nested" ] || { echo "file in a subdirectory changed"; return 1; }
}

test_prune_old_archives() {
    local t="/tmp/rl prune" logs archive day f
    new_tree "$t"
    logs="$t/logs dir"
    archive="$t/archive dir"
    mkdir -p "$logs" "$archive"
    printf 'export done\n' >"$logs/export errors.log"
    printf 'POST /charge 201\n' >"$logs/api.log"
    for day in 13 14 15 16 17; do
        f="$archive/export errors-202611${day}T021500Z.log.gz"
        echo "old $day" | gzip -c >"$f"
        sha256sum "$f" | awk '{print $1}' >"$f.sha256"
        touch -d "2026-11-$day 02:15:00" "$f" "$f.sha256"
    done
    for day in 16 17; do
        f="$archive/api-202611${day}T021500Z.log.gz"
        echo "old $day" | gzip -c >"$f"
        sha256sum "$f" | awk '{print $1}' >"$f.sha256"
        touch -d "2026-11-$day 02:15:00" "$f" "$f.sha256"
    done
    printf 'archive of the billing logs\n' >"$archive/README.txt"
    KEEP=3 run_script "$logs" "$archive" || { echo "exit status $?"; return 1; }
    local expected actual
    expected=$(printf '%s\n' \
        "README.txt" \
        "api-20261116T021500Z.log.gz" "api-20261116T021500Z.log.gz.sha256" \
        "api-20261117T021500Z.log.gz" "api-20261117T021500Z.log.gz.sha256" \
        "api-$STAMP_NEW.log.gz" "api-$STAMP_NEW.log.gz.sha256" \
        "export errors-20261116T021500Z.log.gz" "export errors-20261116T021500Z.log.gz.sha256" \
        "export errors-20261117T021500Z.log.gz" "export errors-20261117T021500Z.log.gz.sha256" \
        "export errors-$STAMP_NEW.log.gz" "export errors-$STAMP_NEW.log.gz.sha256" | LC_ALL=C sort)
    actual=$(cd "$archive" && find . -mindepth 1 -printf '%P\n' | LC_ALL=C sort)
    if [ "$expected" != "$actual" ]; then
        echo "archive directory content is wrong:"
        diff <(echo "$expected") <(echo "$actual")
        return 1
    fi
}

make_failing_gzip() {
    mkdir -p /tmp/rl-stubs
    cat >/tmp/rl-stubs/gzip <<'EOF'
#!/bin/sh
# Simulates a full archive volume: a few bytes of output, then an error.
printf '\037\213\010\000'
echo "gzip: stdout: No space left on device" >&2
exit 1
EOF
    chmod +x /tmp/rl-stubs/gzip
}

test_failed_compression_keeps_log() {
    local t=/tmp/rl-fail rc content
    new_tree "$t"
    mkdir -p "$t"/logs
    content=$(printf 'invoice 1001 exported\ninvoice 1002 exported')
    printf '%s\n' "$content" >"$t"/logs/billing.log
    make_failing_gzip
    PATH=/tmp/rl-stubs:$PATH KEEP=14 run_script "$t"/logs "$t"/archive
    rc=$?
    [ "$rc" -ne 0 ] || { echo "exit status 0 after a failed archive"; return 1; }
    [ "$rc" -ne 124 ] || { echo "the script did not finish"; return 1; }
    [ "$(cat "$t"/logs/billing.log)" = "$content" ] || { echo "billing.log was changed"; return 1; }
}

test_failed_compression_with_spaces() {
    local t="/tmp/rl fail spaces" rc content
    new_tree "$t"
    mkdir -p "$t/logs"
    content="payout batch 7 sent"
    printf '%s\n' "$content" >"$t/logs/export errors.log"
    make_failing_gzip
    PATH=/tmp/rl-stubs:$PATH KEEP=14 run_script "$t/logs" "$t/archive"
    rc=$?
    [ "$rc" -ne 0 ] && [ "$rc" -ne 124 ] || { echo "exit status $rc after a failed archive"; return 1; }
    [ "$(cat "$t/logs/export errors.log")" = "$content" ] || { echo "export errors.log was changed"; return 1; }
}

test_shellcheck() {
    shellcheck "$SCRIPT"
}

if [ ! -f "$SCRIPT" ]; then
    echo "missing $SCRIPT"
fi

check plain_paths test_plain_paths
check spaces_in_paths test_spaces_in_paths
check prune_old_archives test_prune_old_archives
check failed_archive_keeps_log test_failed_compression_keeps_log
check failed_archive_with_spaces test_failed_compression_with_spaces
check shellcheck_clean test_shellcheck

write_result
exit 0
