#!/usr/bin/env bash
# Hidden check of the hard-ops-release task: behavior of bin/relctl in
# scratch trees below /tmp, with paths that contain spaces and glob
# characters, and shellcheck on the script. Each check names the rules of
# docs/REQUIREMENTS.md that it tests.
# The test functions run through "check" from lib.sh.
# shellcheck disable=SC2015,SC2016,SC2317,SC2329
set -u
VERIFY_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
. "$VERIFY_DIR/lib.sh"

SCRIPT=/work/bin/relctl
ROOT="/tmp/relctl check"
STDERR_ALL="$ROOT/all-stderr.txt"
ERRLESS="$ROOT/exit-without-error-line.txt"
unset RELCTL_CONFIG RELCTL_BASE RELCTL_KEEP RELCTL_LOCK_WAIT
rm -rf "$ROOT"
mkdir -p "$ROOT"
: >"$STDERR_ALL"
: >"$ERRLESS"

# Helpers

# new_sandbox NAME: set SB (scratch dir), BASE (base dir, not made), CONF
# (configuration path), PKGS (package dir).
new_sandbox() {
    SB="$ROOT/$1"
    rm -rf "$SB"
    mkdir -p "$SB/conf dir" "$SB/pkgs [1]"
    BASE="$SB/srv *app* [x]"
    CONF="$SB/conf dir/relctl *.conf"
    PKGS="$SB/pkgs [1]"
    RENV=()
}

# write_conf LINE...: write the configuration file, one line for each argument.
write_conf() {
    printf '%s\n' "$@" >"$CONF"
}

# make_pkg PATH VERSION [CONTENT [STYLE]]: make a package and PATH.sha256.
# STYLE "dot" (default) gives member names with "./", "plain" without.
make_pkg() {
    local pkg=$1 version=$2 content=${3:-"app $2"} style=${4:-dot} src sum
    src=$(mktemp -d "$ROOT/src.XXXXXX")
    mkdir -p "$src/bin" "$src/var/data" "$src/etc"
    printf '%s\n' "$version" >"$src/VERSION"
    printf '#!/bin/sh\necho %s\n' "$content" >"$src/bin/app"
    chmod 755 "$src/bin/app"
    printf 'seed %s\n' "$version" >"$src/var/data/seed.txt"
    printf 'name=app\n' >"$src/etc/app.conf"
    if [ "$style" = plain ]; then
        tar -czf "$pkg" -C "$src" VERSION bin var etc
    else
        tar -czf "$pkg" -C "$src" .
    fi
    rm -rf "$src"
    sum=$(sha256sum <"$pkg")
    printf '%s  %s\n' "${sum%% *}" "$(basename -- "$pkg")" >"$pkg.sha256"
}

# make_raw_pkg PATH NAME=CONTENT...: a package with exactly these regular
# files (names as given, also unsafe ones), and PATH.sha256.
make_raw_pkg() {
    local pkg=$1 sum
    shift
    python3 - "$pkg" "$@" <<'EOF'
import io, sys, tarfile
with tarfile.open(sys.argv[1], "w:gz") as tar:
    for item in sys.argv[2:]:
        name, _, content = item.partition("=")
        data = content.encode()
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(data))
EOF
    sum=$(sha256sum <"$pkg")
    printf '%s  %s\n' "${sum%% *}" "$(basename -- "$pkg")" >"$pkg.sha256"
}

sha_of() {
    local sum
    sum=$(sha256sum <"$1")
    printf '%s' "${sum%% *}"
}

# R ARG...: run relctl. RC gets the exit code, $SB/out the stdout, $SB/err
# the stderr. RENV holds extra environment assignments.
# Each call has a limit of 20 s, and after 200 s of verify.sh no call runs,
# so that a script that hangs gives failed checks within the 300 s limit.
R() {
    if [ "$SECONDS" -gt 200 ]; then
        echo "verify.sh time budget used up" >"$SB/err"
        : >"$SB/out"
        RC=124
        return
    fi
    timeout 20 env "${RENV[@]}" bash "$SCRIPT" "$@" >"$SB/out" 2>"$SB/err" </dev/null
    RC=$?
    record_stderr "$RC" "$SB/err" "$*"
}

record_stderr() {
    cat "$2" >>"$STDERR_ALL"
    if [ "$1" -ne 0 ] && ! grep -q '^relctl: error: .' "$2"; then
        printf 'exit %s without an error line: %s\n' "$1" "$3" >>"$ERRLESS"
    fi
}

expect_rc() {
    local want=$1 what=$2
    if [ "$RC" -ne "$want" ]; then
        echo "$what: exit code $RC, expected $want"
        sed 's/^/    stderr: /' "$SB/err" | head -n 5
        return 1
    fi
}

current_target() {
    readlink -- "$BASE/current" 2>/dev/null
}

expect_current() {
    local want=$1 got
    got=$(current_target)
    if [ "$want" = none ]; then
        if [ -e "$BASE/current" ] || [ -L "$BASE/current" ]; then
            echo "current exists ($got), expected none"
            return 1
        fi
        return 0
    fi
    [ "$got" = "releases/$want" ] || { echo "current points to '$got', expected 'releases/$want'"; return 1; }
}

# releases: the release directories, sorted, on one line.
releases() {
    [ -d "$BASE/releases" ] || return 0
    find "$BASE/releases" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | LC_ALL=C sort | paste -sd ' ' -
}

expect_releases() {
    local got
    got=$(releases)
    [ "$got" = "$1" ] || { echo "releases are '$got', expected '$1'"; return 1; }
}

history_lines() {
    if [ -f "$BASE/history.tsv" ]; then
        wc -l <"$BASE/history.tsv"
    else
        echo 0
    fi
}

# expect_last_history ACTION VERSION SHA: the last history line.
expect_last_history() {
    local line
    line=$(tail -n 1 "$BASE/history.tsv" 2>/dev/null)
    if ! awk -F'\t' -v a="$1" -v v="$2" -v s="$3" '
        NF == 4 && $1 ~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z$/ &&
        $2 == a && $3 == v && $4 == s { ok = 1 } END { exit !ok }' <<<"$line"; then
        echo "last history line is '$line', expected '<time>	$1	$2	$3'"
        return 1
    fi
}

staging_empty() {
    if [ -d "$BASE/.staging" ] && [ -n "$(find "$BASE/.staging" -mindepth 1 -print -quit)" ]; then
        echo ".staging is not empty:"
        find "$BASE/.staging" -mindepth 1 | head -n 5
        return 1
    fi
}

# snapshot DIR: a listing of all paths with type, symlink target and content
# hash. The lock file and the .staging directory itself (not its content) are
# not in it: R12 permits an empty .staging.
snapshot() {
    [ -e "$1" ] || { echo "(missing)"; return 0; }
    (
        cd "$1" || exit 1
        find . -mindepth 1 ! -path ./.relctl.lock ! -path ./.staging -printf '%p|%y|%l\n' | LC_ALL=C sort
        find . -type f ! -path ./.relctl.lock -print0 | LC_ALL=C sort -z | xargs -0r sha256sum
    )
}

proc_running() {
    local state
    [ -r "/proc/$1/status" ] || return 1
    state=$(awk '/^State:/ { print $2 }' "/proc/$1/status" 2>/dev/null)
    [ -n "$state" ] && [ "$state" != Z ]
}

# wait_gone PID SECONDS: wait until the process stopped. Fails on the time limit.
wait_gone() {
    local pid=$1 limit=$(($2 * 10)) i=0
    while proc_running "$pid"; do
        i=$((i + 1))
        [ "$i" -le "$limit" ] || return 1
        sleep 0.1
    done
}

# wait_file PATH SECONDS
wait_file() {
    local limit=$(($2 * 10)) i=0
    while [ ! -s "$1" ]; do
        i=$((i + 1))
        [ "$i" -le "$limit" ] || return 1
        sleep 0.1
    done
}

# make_hook PATH: a health check that writes its environment to PATH.env,
# writes "hook stdout" and "hook stderr", fails for versions listed in
# PATH.fail, and for versions listed in PATH.block writes its PID to
# PATH.pid and waits (at most 30 s) for the file PATH.go.
make_hook() {
    local hook=$1 q
    printf -v q '%q' "$hook"
    cat >"$hook" <<EOF
#!/bin/bash
hook=$q
{
    echo "version=\$RELCTL_VERSION"
    echo "dir=\$RELCTL_RELEASE_DIR"
    echo "pwd=\$(pwd -P)"
} >"\$hook.env"
echo "hook stdout"
echo "hook stderr" >&2
if [ -f "\$hook.block" ] && grep -qxF -- "\$RELCTL_VERSION" "\$hook.block"; then
    echo \$\$ >"\$hook.pid"
    for _ in \$(seq 300); do
        [ -e "\$hook.go" ] && exit 0
        sleep 0.1
    done
    exit 0
fi
if [ -f "\$hook.fail" ] && grep -qxF -- "\$RELCTL_VERSION" "\$hook.fail"; then
    exit 1
fi
exit 0
EOF
    chmod 755 "$hook"
}

# install_versions VERSION...: install packages with these versions (extra args from INSTALL_ARGS).
install_versions() {
    local v
    for v in "$@"; do
        make_pkg "$PKGS/app-$v.tar.gz" "$v"
        R "${INSTALL_ARGS[@]}" install "$PKGS/app-$v.tar.gz"
        expect_rc 0 "install $v" || return 1
    done
}

# Checks

test_usage_errors() { # R1, R2
    new_sandbox usage
    write_conf "base_dir=$BASE"
    make_pkg "$PKGS/app-1.0.0.tar.gz" 1.0.0
    R --config "$CONF" deploy
    expect_rc 2 "unknown command" || return 1
    R --config "$CONF" --frobnicate status
    expect_rc 2 "unknown option" || return 1
    R --config "$CONF"
    expect_rc 2 "no command" || return 1
    R --config "$CONF" install
    expect_rc 2 "install without a package" || return 1
    R --config "$CONF" install "$PKGS/app-1.0.0.tar.gz" extra
    expect_rc 2 "install with two arguments" || return 1
    R --config "$CONF" status extra
    expect_rc 2 "status with an argument" || return 1
    R --config "$CONF" rollback now
    expect_rc 2 "rollback with an argument" || return 1
    R --config "$CONF" --keep
    expect_rc 2 "--keep without a value" || return 1
    [ ! -e "$BASE/releases/1.0.0" ] || { echo "a usage error installed a release"; return 1; }
}

test_install_basic() { # R1, R3, R10, R13, R16, R19, R26
    local sum1 sum2
    new_sandbox basic
    write_conf "base_dir=$BASE"
    make_pkg "$PKGS/-hot fix 2.0.0.tar.gz" 2.0.0 "two zero"
    make_pkg "$PKGS/app *2.1.0*.tar.gz" 2.1.0 "two one" plain
    sum1=$(sha_of "$PKGS/-hot fix 2.0.0.tar.gz")
    sum2=$(sha_of "$PKGS/app *2.1.0*.tar.gz")
    # A relative package path that begins with "-", from another directory.
    (
        cd "$PKGS" || exit 1
        R --config "$CONF" install "-hot fix 2.0.0.tar.gz"
        echo "$RC" >"$SB/rc"
    )
    RC=$(cat "$SB/rc")
    expect_rc 0 "install of '-hot fix 2.0.0.tar.gz' (relative path)" || return 1
    [ ! -s "$SB/out" ] || { echo "install wrote to stdout"; return 1; }
    expect_current 2.0.0 || return 1
    [ "$(sh "$BASE/current/bin/app")" = "two zero" ] || { echo "wrong content in releases/2.0.0"; return 1; }
    [ "$(cat "$BASE/releases/2.0.0/VERSION")" = 2.0.0 ] || { echo "VERSION is not at the top of the release"; return 1; }
    [ "$(history_lines)" -eq 1 ] || { echo "history has $(history_lines) lines, expected 1"; return 1; }
    expect_last_history install 2.0.0 "$sum1" || return 1
    staging_empty || return 1
    R --config "$CONF" install "$PKGS/app *2.1.0*.tar.gz"
    expect_rc 0 "install of a package with member names without ./" || return 1
    expect_current 2.1.0 || return 1
    [ "$(sh "$BASE/current/bin/app")" = "two one" ] || { echo "wrong content in releases/2.1.0"; return 1; }
    [ "$(history_lines)" -eq 2 ] || { echo "history has $(history_lines) lines, expected 2"; return 1; }
    expect_last_history install 2.1.0 "$sum2" || return 1
    expect_releases "2.0.0 2.1.0" || return 1
    staging_empty
}

test_config_parsing() { # R5, R6, R7, R23
    local v
    new_sandbox parsing
    INSTALL_ARGS=(--config "$CONF")
    printf '%s\n' \
        "# relctl configuration" \
        "   # an indented comment" \
        "" \
        "  	 " \
        "   base_dir=$BASE" \
        "keep=08	 " \
        "lock_wait=0005" \
        "	health_timeout=030" \
        "shared=var/up loads" >"$CONF"
    for v in 1 2 3 4 5 6 7 8 9 10; do
        install_versions "1.0.$v" || return 1
    done
    expect_releases "1.0.10 1.0.3 1.0.4 1.0.5 1.0.6 1.0.7 1.0.8 1.0.9" || return 1
    [ -L "$BASE/releases/1.0.10/var/up loads" ] || { echo "shared path with a space is not a symlink"; return 1; }
}

# config_case NAME EXPECTED_RC CONFIG_LINE...: a fresh base dir, then install.
config_case() {
    local name=$1 want=$2
    shift 2
    BASE="$SB/base $name"
    printf '%s\n' "$@" >"$CONF"
    R --config "$CONF" install "$PKGS/app-1.0.0.tar.gz"
    expect_rc "$want" "configuration case '$name'" || return 1
    if [ "$want" -ne 0 ] && [ -e "$BASE" ]; then
        echo "configuration case '$name': the base dir was made"
        return 1
    fi
}

test_config_errors() { # R4 to R9
    local pwned="$ROOT/pwned" c
    new_sandbox config
    make_pkg "$PKGS/app-1.0.0.tar.gz" 1.0.0
    rm -f "$pwned"-*
    c() { config_case "$@" || return 1; }
    c control 0 "base_dir=$SB/base control" "keep=5" || return 1
    c unknown-key 3 "base_dir=$SB/base unknown-key" "colour=blue" || return 1
    c no-equals 3 "base_dir=$SB/base no-equals" "keep" || return 1
    c spaces-around 3 "base_dir=$SB/base spaces-around" "keep = 5" || return 1
    c duplicate 3 "base_dir=$SB/base duplicate" "keep=3" "keep=4" || return 1
    c keep-low 3 "base_dir=$SB/base keep-low" "keep=1" || return 1
    c keep-high 3 "base_dir=$SB/base keep-high" "keep=51" || return 1
    c keep-sign 3 "base_dir=$SB/base keep-sign" "keep=+3" || return 1
    c keep-text 3 "base_dir=$SB/base keep-text" "keep=5x" || return 1
    c keep-empty 3 "base_dir=$SB/base keep-empty" "keep=" || return 1
    c keep-long 3 "base_dir=$SB/base keep-long" "keep=00005" || return 1
    c lock-high 3 "base_dir=$SB/base lock-high" "lock_wait=601" || return 1
    c timeout-zero 3 "base_dir=$SB/base timeout-zero" "health_timeout=0" || return 1
    c health-relative 3 "base_dir=$SB/base health-relative" "health_cmd=bin/check" || return 1
    c health-missing 3 "base_dir=$SB/base health-missing" "health_cmd=$SB/no such check" || return 1
    c health-subst 3 "base_dir=$SB/base health-subst" "health_cmd=\$(touch '$pwned-1')" || return 1
    c keep-subst 3 "base_dir=$SB/base keep-subst" "keep=5; touch '$pwned-2'" || return 1
    c base-subst 3 "base_dir=\$(touch '$pwned-3')/srv" || return 1
    c base-relative 3 "base_dir=srv/app" || return 1
    c no-base 3 "keep=5" || return 1
    c shared-dotdot 3 "base_dir=$SB/base shared-dotdot" "shared=../escape" || return 1
    c shared-absolute 3 "base_dir=$SB/base shared-absolute" "shared=/var/data" || return 1
    c shared-empty-name 3 "base_dir=$SB/base shared-empty-name" "shared=var//data" || return 1
    c shared-dot 3 "base_dir=$SB/base shared-dot" "shared=var/./data" || return 1
    c shared-trailing 3 "base_dir=$SB/base shared-trailing" "shared=var/data/" || return 1
    if compgen -G "$pwned-*" >/dev/null; then
        echo "a configuration value ran as shell code"
        return 1
    fi
    # The value has inner spaces and quotes as normal text.
    c base-quotes 0 "base_dir=$SB/base \"quoted\" dir" || return 1
    [ -L "$SB/base \"quoted\" dir/current" ] || { echo "base_dir with quotes was not used as text"; return 1; }
    # Configuration files that do not exist.
    BASE="$SB/base missing"
    R --config "$SB/no such.conf" --base "$BASE" install "$PKGS/app-1.0.0.tar.gz"
    expect_rc 3 "--config with a missing file" || return 1
    RENV=("RELCTL_CONFIG=$SB/no such.conf")
    R --base "$BASE" install "$PKGS/app-1.0.0.tar.gz"
    expect_rc 3 "RELCTL_CONFIG with a missing file" || return 1
    RENV=()
    # Bad values from options and from the environment.
    printf 'base_dir=%s\n' "$BASE" >"$CONF"
    R --config "$CONF" --keep abc install "$PKGS/app-1.0.0.tar.gz"
    expect_rc 3 "--keep abc" || return 1
    R --config "$CONF" --base relative/dir install "$PKGS/app-1.0.0.tar.gz"
    expect_rc 3 "--base with a relative path" || return 1
    RENV=("RELCTL_LOCK_WAIT=601")
    R --config "$CONF" install "$PKGS/app-1.0.0.tar.gz"
    expect_rc 3 "RELCTL_LOCK_WAIT=601" || return 1
    RENV=()
    [ ! -e "$BASE" ] || { echo "a configuration error made the base dir"; return 1; }
}

test_precedence() { # R4, R8
    local a b c d conf2="$SB/conf dir/second.conf"
    new_sandbox precedence
    conf2="$SB/conf dir/second.conf"
    a="$SB/base a" b="$SB/base b" c="$SB/base c"
    make_pkg "$PKGS/app-1.0.0.tar.gz" 1.0.0
    printf 'base_dir=%s\n' "$a" >"$CONF"
    BASE=$c
    RENV=("RELCTL_BASE=$b")
    R --config "$CONF" --base "$c" install "$PKGS/app-1.0.0.tar.gz"
    expect_rc 0 "install with --base" || return 1
    [ -L "$c/current" ] && [ ! -e "$b" ] && [ ! -e "$a" ] || { echo "--base did not win over RELCTL_BASE and base_dir"; return 1; }
    R --config "$CONF" install "$PKGS/app-1.0.0.tar.gz"
    expect_rc 0 "install with RELCTL_BASE" || return 1
    [ -L "$b/current" ] && [ ! -e "$a" ] || { echo "RELCTL_BASE did not win over base_dir"; return 1; }
    RENV=("RELCTL_BASE=")
    R --config "$CONF" install "$PKGS/app-1.0.0.tar.gz"
    expect_rc 0 "install with base_dir (empty RELCTL_BASE)" || return 1
    [ -L "$a/current" ] || { echo "base_dir was not used"; return 1; }
    # RELCTL_CONFIG is used without --config, and --config wins over it.
    d="$SB/base d"
    printf 'base_dir=%s\n' "$d" >"$conf2"
    RENV=("RELCTL_CONFIG=$conf2")
    R install "$PKGS/app-1.0.0.tar.gz"
    expect_rc 0 "install with RELCTL_CONFIG" || return 1
    [ -L "$d/current" ] || { echo "RELCTL_CONFIG was not used"; return 1; }
    rm -rf "$a"
    R --config "$CONF" install "$PKGS/app-1.0.0.tar.gz"
    expect_rc 0 "install with --config and RELCTL_CONFIG" || return 1
    [ -L "$a/current" ] || { echo "--config did not win over RELCTL_CONFIG"; return 1; }
    # keep: option, then environment, then file.
    BASE="$SB/base keep"
    printf 'base_dir=%s\nkeep=50\n' "$BASE" >"$CONF"
    RENV=()
    INSTALL_ARGS=(--config "$CONF")
    install_versions 1.0.1 1.0.2 1.0.3 1.0.4 1.0.5 1.0.6 || return 1
    printf 'base_dir=%s\nkeep=5\n' "$BASE" >"$conf2"
    R --config "$conf2" prune
    expect_rc 0 "prune with keep=5 in the file" || return 1
    expect_releases "1.0.2 1.0.3 1.0.4 1.0.5 1.0.6" || return 1
    RENV=("RELCTL_KEEP=4")
    R --config "$conf2" prune
    expect_rc 0 "prune with RELCTL_KEEP=4" || return 1
    expect_releases "1.0.3 1.0.4 1.0.5 1.0.6" || return 1
    RENV=("RELCTL_KEEP=abc")
    R --config "$conf2" --keep 3 prune
    expect_rc 0 "prune with --keep 3 and a bad RELCTL_KEEP" || return 1
    expect_releases "1.0.4 1.0.5 1.0.6" || return 1
    R --config "$conf2" prune
    expect_rc 3 "prune with RELCTL_KEEP=abc" || return 1
    RENV=()
}

test_package_checks() { # R11, R12
    local before p
    new_sandbox package
    write_conf "base_dir=$BASE"
    INSTALL_ARGS=(--config "$CONF")
    install_versions 1.0.0 || return 1
    before=$(snapshot "$BASE")
    # bad_case NAME PACKAGE: install must exit 4 and change nothing.
    bad_case() {
        R --config "$CONF" install "$2"
        expect_rc 4 "package case '$1'" || return 1
        [ "$(snapshot "$BASE")" = "$before" ] || { echo "package case '$1' changed the base dir"; return 1; }
    }
    bad_case missing-package "$PKGS/no such.tar.gz" || return 1
    make_pkg "$PKGS/no sum.tar.gz" 1.1.0
    rm -f "$PKGS/no sum.tar.gz.sha256"
    bad_case missing-checksum "$PKGS/no sum.tar.gz" || return 1
    make_pkg "$PKGS/wrong sum.tar.gz" 1.1.0
    make_pkg "$PKGS/other.tar.gz" 1.1.0 other
    cp "$PKGS/other.tar.gz.sha256" "$PKGS/wrong sum.tar.gz.sha256"
    bad_case wrong-checksum "$PKGS/wrong sum.tar.gz" || return 1
    make_pkg "$PKGS/short sum.tar.gz" 1.1.0
    sed -i 's/^\(.\{63\}\)./\1/' "$PKGS/short sum.tar.gz.sha256"
    bad_case short-checksum "$PKGS/short sum.tar.gz" || return 1
    printf 'not a tar file\n' >"$PKGS/text.tar.gz"
    p=$(sha_of "$PKGS/text.tar.gz")
    printf '%s\n' "$p" >"$PKGS/text.tar.gz.sha256"
    bad_case not-a-tar "$PKGS/text.tar.gz" || return 1
    make_raw_pkg "$PKGS/two-part.tar.gz" "VERSION=1.2"$'\n' "bin/app=x" && bad_case version-1.2 "$PKGS/two-part.tar.gz" || return 1
    make_raw_pkg "$PKGS/v-prefix.tar.gz" "VERSION=v1.2.3"$'\n' && bad_case version-v-prefix "$PKGS/v-prefix.tar.gz" || return 1
    make_raw_pkg "$PKGS/two-lines.tar.gz" "VERSION=1.2.3"$'\n'"1.2.4"$'\n' && bad_case version-two-lines "$PKGS/two-lines.tar.gz" || return 1
    make_raw_pkg "$PKGS/two-newlines.tar.gz" "VERSION=1.2.3"$'\n\n' && bad_case version-two-newlines "$PKGS/two-newlines.tar.gz" || return 1
    make_raw_pkg "$PKGS/no-version.tar.gz" "bin/app=x" && bad_case no-version "$PKGS/no-version.tar.gz" || return 1
    make_raw_pkg "$PKGS/nested-version.tar.gz" "app/VERSION=1.2.3"$'\n' && bad_case nested-version "$PKGS/nested-version.tar.gz" || return 1
    make_raw_pkg "$PKGS/dotdot.tar.gz" "VERSION=1.2.3"$'\n' "../escaped by dotdot=x" &&
        bad_case dotdot-member "$PKGS/dotdot.tar.gz" || return 1
    make_raw_pkg "$PKGS/dotdot-inner.tar.gz" "VERSION=1.2.3"$'\n' "bin/../../escaped inner=x" &&
        bad_case dotdot-inner-member "$PKGS/dotdot-inner.tar.gz" || return 1
    make_raw_pkg "$PKGS/absolute.tar.gz" "VERSION=1.2.3"$'\n' "$ROOT/escaped absolute=x" &&
        bad_case absolute-member "$PKGS/absolute.tar.gz" || return 1
    if [ -e "$SB/escaped by dotdot" ] || [ -e "$ROOT/escaped absolute" ] || [ -e "$PKGS/escaped by dotdot" ]; then
        echo "a member outside the release was written"
        return 1
    fi
    # Valid variants: upper case SHA-256 with no file name, no final newline in VERSION.
    make_raw_pkg "$PKGS/upper.tar.gz" "VERSION=1.2.0-rc.1" "bin/app=x"
    p=$(sha_of "$PKGS/upper.tar.gz")
    printf '%s\n' "${p^^}" >"$PKGS/upper.tar.gz.sha256"
    R --config "$CONF" install "$PKGS/upper.tar.gz"
    expect_rc 0 "upper case SHA-256 and VERSION without a newline" || return 1
    expect_current 1.2.0-rc.1 || return 1
    expect_last_history install 1.2.0-rc.1 "$p"
}

test_same_version() { # R14, R19
    local lines sum_a
    new_sandbox same
    write_conf "base_dir=$BASE"
    make_pkg "$PKGS/a.tar.gz" 1.0.0 "first build"
    make_pkg "$PKGS/a-rebuilt.tar.gz" 1.0.0 "second build"
    make_pkg "$PKGS/b.tar.gz" 1.1.0
    sum_a=$(sha_of "$PKGS/a.tar.gz")
    R --config "$CONF" install "$PKGS/a.tar.gz"
    expect_rc 0 "first install" || return 1
    lines=$(history_lines)
    R --config "$CONF" install "$PKGS/a.tar.gz"
    expect_rc 0 "install of the current version again" || return 1
    [ "$(history_lines)" -eq "$lines" ] || { echo "a no-op install wrote a history line"; return 1; }
    expect_current 1.0.0 || return 1
    R --config "$CONF" install "$PKGS/a-rebuilt.tar.gz"
    expect_rc 5 "same version, other package (current)" || return 1
    [ "$(sh "$BASE/releases/1.0.0/bin/app")" = "first build" ] || { echo "release 1.0.0 was changed"; return 1; }
    [ "$(history_lines)" -eq "$lines" ] || { echo "a conflict wrote a history line"; return 1; }
    R --config "$CONF" install "$PKGS/b.tar.gz"
    expect_rc 0 "install of 1.1.0" || return 1
    R --config "$CONF" install "$PKGS/a-rebuilt.tar.gz"
    expect_rc 5 "same version, other package (not current)" || return 1
    expect_current 1.1.0 || return 1
    echo "marker" >"$BASE/releases/1.0.0/marker.txt"
    R --config "$CONF" install "$PKGS/a.tar.gz"
    expect_rc 0 "activation of the installed 1.0.0" || return 1
    expect_current 1.0.0 || return 1
    [ -f "$BASE/releases/1.0.0/marker.txt" ] || { echo "release 1.0.0 was unpacked again"; return 1; }
    expect_last_history install 1.0.0 "$sum_a" || return 1
    R --config "$CONF" status
    expect_rc 0 "status" || return 1
    grep -qx 'releases=1.0.0 1.1.0' "$SB/out" || { echo "status shows: $(grep '^releases=' "$SB/out")"; return 1; }
}

test_shared_links() { # R15
    new_sandbox shared
    write_conf "base_dir=$BASE" "shared=var/data" "shared=logs dir" "shared=cache/a b*"
    mkdir -p "$BASE/shared/var/data"
    echo "keep me" >"$BASE/shared/var/data/keep.txt"
    INSTALL_ARGS=(--config "$CONF")
    install_versions 1.0.0 || return 1
    local rel="$BASE/releases/1.0.0" p
    for p in "var/data" "logs dir" "cache/a b*"; do
        [ -L "$rel/$p" ] || { echo "$p is not a symlink in the release"; return 1; }
        [ "$(readlink -- "$rel/$p")" = "$BASE/shared/$p" ] ||
            { echo "$p points to '$(readlink -- "$rel/$p")', expected '$BASE/shared/$p'"; return 1; }
        [ -d "$BASE/shared/$p" ] || { echo "shared/$p is not a directory"; return 1; }
    done
    [ -d "$rel/cache" ] && [ ! -L "$rel/cache" ] || { echo "the parent cache/ is not a directory in the release"; return 1; }
    [ "$(cat "$rel/var/data/keep.txt")" = "keep me" ] || { echo "shared content is not visible"; return 1; }
    [ ! -e "$BASE/shared/var/data/seed.txt" ] || { echo "the release content was put into shared/"; return 1; }
    [ "$(find "$BASE/shared" -type f | wc -l)" -eq 1 ] || { echo "the content of shared/ changed"; return 1; }
    [ -f "$rel/etc/app.conf" ] || { echo "other release content is missing"; return 1; }
    echo "written by 1.0.0" >"$rel/logs dir/app.log"
    install_versions 1.1.0 || return 1
    [ "$(cat "$BASE/releases/1.1.0/logs dir/app.log")" = "written by 1.0.0" ] || { echo "1.1.0 does not share logs dir"; return 1; }
}

test_health_check() { # R3, R17
    local hook="$SB/hooks dir/check *"
    new_sandbox health
    hook="$SB/hooks dir/check *"
    mkdir -p "$SB/hooks dir"
    make_hook "$hook"
    write_conf "base_dir=$BASE" "health_cmd=$hook"
    INSTALL_ARGS=(--config "$CONF")
    install_versions 3.0.0 || return 1
    grep -qx "version=3.0.0" "$hook.env" || { echo "RELCTL_VERSION is wrong:"; cat "$hook.env"; return 1; }
    grep -qxF "dir=$BASE/releases/3.0.0" "$hook.env" || { echo "RELCTL_RELEASE_DIR is wrong:"; cat "$hook.env"; return 1; }
    grep -qxF "pwd=$(cd "$BASE/releases/3.0.0" && pwd -P)" "$hook.env" || { echo "the working directory is wrong:"; cat "$hook.env"; return 1; }
    grep -qx "hook stdout" "$BASE/health.log" && grep -qx "hook stderr" "$BASE/health.log" ||
        { echo "health.log does not have the output of the health check"; return 1; }
    ! grep -q 'hook std' "$SB/err" || { echo "output of the health check is on stderr"; return 1; }
    [ ! -s "$SB/out" ] || { echo "install wrote to stdout"; return 1; }
    # current points to the new release while the check runs.
    cat >"$SB/hooks dir/current check" <<EOF
#!/bin/bash
[ "\$(readlink "$BASE/current")" = "releases/\$RELCTL_VERSION" ]
EOF
    chmod 755 "$SB/hooks dir/current check"
    write_conf "base_dir=$BASE" "health_cmd=$SB/hooks dir/current check"
    install_versions 3.1.0 || return 1
    expect_current 3.1.0
}

test_health_failure() { # R18, R19
    local hook sum lines
    new_sandbox healthfail
    hook="$SB/hooks/check"
    mkdir -p "$SB/hooks"
    make_hook "$hook"
    echo 2.0.0 >"$hook.fail"
    write_conf "base_dir=$BASE" "health_cmd=$hook" "keep=2"
    INSTALL_ARGS=(--config "$CONF")
    install_versions 1.0.0 1.1.0 || return 1
    make_pkg "$PKGS/app-2.0.0.tar.gz" 2.0.0
    sum=$(sha_of "$PKGS/app-2.0.0.tar.gz")
    lines=$(history_lines)
    R --config "$CONF" install "$PKGS/app-2.0.0.tar.gz"
    expect_rc 6 "install with a failed health check" || return 1
    expect_current 1.1.0 || return 1
    [ ! -e "$BASE/releases/2.0.0" ] || { echo "releases/2.0.0 was not removed"; return 1; }
    expect_releases "1.0.0 1.1.0" || return 1
    [ "$(history_lines)" -eq $((lines + 1)) ] || { echo "expected one new history line"; return 1; }
    expect_last_history failed 2.0.0 "$sum" || return 1
    staging_empty || return 1
    # The first install fails: no current after it.
    new_sandbox healthfirst
    mkdir -p "$SB/hooks"
    make_hook "$SB/hooks/check"
    echo 2.0.0 >"$SB/hooks/check.fail"
    write_conf "base_dir=$BASE" "health_cmd=$SB/hooks/check"
    make_pkg "$PKGS/app-2.0.0.tar.gz" 2.0.0
    R --config "$CONF" install "$PKGS/app-2.0.0.tar.gz"
    expect_rc 6 "first install with a failed health check" || return 1
    expect_current none || return 1
    [ ! -e "$BASE/releases/2.0.0" ] || { echo "releases/2.0.0 was not removed"; return 1; }
    # A failed activation of an existing release keeps it.
    new_sandbox healthagain
    mkdir -p "$SB/hooks"
    make_hook "$SB/hooks/check"
    write_conf "base_dir=$BASE" "health_cmd=$SB/hooks/check"
    INSTALL_ARGS=(--config "$CONF")
    install_versions 1.0.0 1.1.0 || return 1
    echo 1.0.0 >"$SB/hooks/check.fail"
    R --config "$CONF" install "$PKGS/app-1.0.0.tar.gz"
    expect_rc 6 "failed activation of the installed 1.0.0" || return 1
    expect_current 1.1.0 || return 1
    [ -f "$BASE/releases/1.0.0/VERSION" ] || { echo "the existing release 1.0.0 was removed"; return 1; }
}

test_health_timeout() { # R17, R18
    local hook start elapsed pid
    new_sandbox timeout
    hook="$SB/hooks/check"
    mkdir -p "$SB/hooks"
    make_hook "$hook"
    write_conf "base_dir=$BASE" "health_cmd=$hook" "health_timeout=1"
    INSTALL_ARGS=(--config "$CONF")
    install_versions 1.0.0 || return 1
    echo 1.1.0 >"$hook.block"
    make_pkg "$PKGS/app-1.1.0.tar.gz" 1.1.0
    start=$SECONDS
    R --config "$CONF" install "$PKGS/app-1.1.0.tar.gz"
    elapsed=$((SECONDS - start))
    pid=$(cat "$hook.pid" 2>/dev/null)
    touch "$hook.go"
    expect_rc 6 "install with a health check that does not end" || return 1
    [ "$elapsed" -le 10 ] || { echo "relctl needed $elapsed s with health_timeout=1"; return 1; }
    [ -n "$pid" ] || { echo "the health check did not start"; return 1; }
    expect_current 1.0.0 || return 1
    [ ! -e "$BASE/releases/1.1.0" ] || { echo "releases/1.1.0 was not removed"; return 1; }
}

test_lock() { # R20
    local holder start elapsed
    new_sandbox lock
    write_conf "base_dir=$BASE"
    INSTALL_ARGS=(--config "$CONF")
    install_versions 1.0.0 || return 1
    make_pkg "$PKGS/app-1.1.0.tar.gz" 1.1.0
    flock -x "$BASE/.relctl.lock" bash -c 'echo x >"$1"; sleep 6' _ "$SB/held" &
    holder=$!
    wait_file "$SB/held" 10 || { echo "the test could not take the lock"; wait "$holder"; return 1; }
    start=$SECONDS
    R --config "$CONF" --lock-wait 1 install "$PKGS/app-1.1.0.tar.gz"
    elapsed=$((SECONDS - start))
    expect_rc 75 "install while the lock is busy" || { wait "$holder"; return 1; }
    [ "$elapsed" -le 4 ] || { echo "relctl waited $elapsed s with --lock-wait 1"; wait "$holder"; return 1; }
    expect_current 1.0.0 || { wait "$holder"; return 1; }
    [ ! -e "$BASE/releases/1.1.0" ] || { echo "a release was installed without the lock"; wait "$holder"; return 1; }
    R --config "$CONF" --lock-wait 0 prune
    expect_rc 75 "prune with --lock-wait 0 while the lock is busy" || { wait "$holder"; return 1; }
    wait "$holder"
    rm -f "$SB/held"
    flock -x "$BASE/.relctl.lock" bash -c 'echo x >"$1"; sleep 1' _ "$SB/held" &
    holder=$!
    wait_file "$SB/held" 10 || { echo "the test could not take the lock"; return 1; }
    R --config "$CONF" --lock-wait 10 install "$PKGS/app-1.1.0.tar.gz"
    wait "$holder"
    expect_rc 0 "install that waits for the lock" || return 1
    expect_current 1.1.0
}

# signal_case SIGNAL EXPECTED_RC
signal_case() {
    local sig=$1 want=$2 hook pid hook_pid rc lines
    new_sandbox "signal $sig"
    hook="$SB/hooks/check"
    mkdir -p "$SB/hooks"
    make_hook "$hook"
    write_conf "base_dir=$BASE" "health_cmd=$hook" "health_timeout=120"
    INSTALL_ARGS=(--config "$CONF")
    install_versions 1.0.0 || return 1
    lines=$(history_lines)
    echo 2.0.0 >"$hook.block"
    make_pkg "$PKGS/app-2.0.0.tar.gz" 2.0.0
    env --default-signal=INT,TERM bash "$SCRIPT" --config "$CONF" install "$PKGS/app-2.0.0.tar.gz" \
        >"$SB/out" 2>"$SB/err" </dev/null &
    pid=$!
    if ! wait_file "$hook.pid" 20; then
        echo "the health check did not start"
        touch "$hook.go"
        wait "$pid"
        return 1
    fi
    hook_pid=$(cat "$hook.pid")
    kill -s "$sig" "$pid"
    if ! wait_gone "$pid" 8; then
        echo "relctl did not stop in 8 s after SIG$sig"
        touch "$hook.go"
        wait "$pid"
        return 1
    fi
    wait "$pid"
    rc=$?
    record_stderr "$rc" "$SB/err" "install with SIG$sig"
    RC=$rc
    if ! wait_gone "$hook_pid" 3; then
        echo "the health check process still runs after relctl stopped"
        touch "$hook.go"
        return 1
    fi
    touch "$hook.go"
    expect_rc "$want" "install stopped by SIG$sig" || return 1
    expect_current 1.0.0 || return 1
    [ ! -e "$BASE/releases/2.0.0" ] || { echo "releases/2.0.0 was not removed"; return 1; }
    staging_empty || return 1
    [ "$(history_lines)" -eq "$lines" ] || { echo "a stopped install wrote a history line"; return 1; }
    # The lock is free again.
    rm -f "$hook.block"
    R --config "$CONF" --lock-wait 0 install "$PKGS/app-2.0.0.tar.gz"
    expect_rc 0 "install after the stopped install" || return 1
    expect_current 2.0.0
}

test_signal_term() { signal_case TERM 143; } # R21
test_signal_int() { signal_case INT 130; }   # R21

test_rollback() { # R19, R22
    local hook before
    new_sandbox rollback
    hook="$SB/hooks/check"
    mkdir -p "$SB/hooks"
    make_hook "$hook"
    write_conf "base_dir=$BASE" "health_cmd=$hook"
    R --config "$CONF" rollback
    expect_rc 7 "rollback with no releases" || return 1
    INSTALL_ARGS=(--config "$CONF")
    install_versions 1.0.0 || return 1
    R --config "$CONF" rollback
    expect_rc 7 "rollback with one release" || return 1
    install_versions 1.1.0 1.2.0 || return 1
    echo 1.1.0 >"$hook.fail"
    R --config "$CONF" rollback
    expect_rc 0 "rollback to 1.1.0 (no health check)" || return 1
    expect_current 1.1.0 || return 1
    expect_last_history rollback 1.1.0 - || return 1
    R --config "$CONF" rollback
    expect_rc 0 "second rollback" || return 1
    expect_current 1.2.0 || return 1
    expect_last_history rollback 1.2.0 - || return 1
    before=$(snapshot "$BASE")
    R --config "$CONF" --dry-run rollback
    expect_rc 0 "rollback --dry-run" || return 1
    [ "$(snapshot "$BASE")" = "$before" ] || { echo "rollback --dry-run changed the base dir"; return 1; }
    # A failed install is not a candidate.
    echo 1.3.0 >"$hook.fail"
    make_pkg "$PKGS/app-1.3.0.tar.gz" 1.3.0
    R --config "$CONF" install "$PKGS/app-1.3.0.tar.gz"
    expect_rc 6 "install of 1.3.0 with a failed health check" || return 1
    R --config "$CONF" status
    grep -qx 'previous=1.1.0' "$SB/out" || { echo "status after a failed install: $(tr '\n' ' ' <"$SB/out")"; return 1; }
    R --config "$CONF" rollback
    expect_rc 0 "rollback after a failed install" || return 1
    expect_current 1.1.0 || return 1
    # A previous release whose directory is gone is not a candidate.
    rm -rf "$BASE/releases/1.2.0"
    R --config "$CONF" rollback
    expect_rc 0 "rollback when the newest candidate is gone" || return 1
    expect_current 1.0.0
}

test_prune() { # R22, R23
    local before
    new_sandbox prune
    write_conf "base_dir=$BASE" "keep=3"
    INSTALL_ARGS=(--config "$CONF")
    install_versions 1.10.0 1.9.0 1.8.0 || return 1
    expect_releases "1.10.0 1.8.0 1.9.0" || return 1
    install_versions 1.11.0 || return 1
    # current 1.11.0, previous 1.8.0, newest other by sort -V: 1.10.0.
    expect_releases "1.10.0 1.11.0 1.8.0" || return 1
    R --config "$CONF" rollback
    expect_rc 0 "rollback to 1.8.0" || return 1
    expect_current 1.8.0 || return 1
    before=$(snapshot "$BASE")
    R --config "$CONF" --dry-run --keep 2 prune
    expect_rc 0 "prune --dry-run" || return 1
    [ "$(snapshot "$BASE")" = "$before" ] || { echo "prune --dry-run changed the base dir"; return 1; }
    R --config "$CONF" --keep 2 prune
    expect_rc 0 "prune --keep 2" || return 1
    expect_releases "1.11.0 1.8.0" || return 1
    expect_current 1.8.0 || return 1
    R --config "$CONF" prune
    expect_rc 0 "prune with nothing to remove" || return 1
    expect_releases "1.11.0 1.8.0"
}

test_dry_run() { # R24
    local hook before holder
    new_sandbox dryrun
    hook="$SB/hooks/check"
    mkdir -p "$SB/hooks"
    make_hook "$hook"
    write_conf "base_dir=$BASE" "health_cmd=$hook"
    make_pkg "$PKGS/app-1.0.0.tar.gz" 1.0.0
    R --config "$CONF" --dry-run install "$PKGS/app-1.0.0.tar.gz"
    expect_rc 0 "install --dry-run on a new base dir" || return 1
    [ ! -e "$BASE" ] || { echo "install --dry-run made the base dir"; return 1; }
    [ ! -e "$hook.env" ] || { echo "install --dry-run ran the health check"; return 1; }
    [ ! -s "$SB/out" ] || { echo "install --dry-run wrote to stdout"; return 1; }
    grep -q '^relctl: \(info\|warn\): .' "$SB/err" || { echo "install --dry-run did not tell what it would do"; return 1; }
    INSTALL_ARGS=(--config "$CONF")
    install_versions 1.0.0 || return 1
    rm -f "$hook.env"
    make_pkg "$PKGS/app-1.1.0.tar.gz" 1.1.0
    make_pkg "$PKGS/app-1.0.0 rebuilt.tar.gz" 1.0.0 rebuilt
    make_pkg "$PKGS/bad sum.tar.gz" 1.2.0
    echo "0000000000000000000000000000000000000000000000000000000000000000" >"$PKGS/bad sum.tar.gz.sha256"
    before=$(snapshot "$BASE")
    R --config "$CONF" --dry-run install "$PKGS/app-1.1.0.tar.gz"
    expect_rc 0 "install --dry-run of 1.1.0" || return 1
    R --config "$CONF" --dry-run install "$PKGS/app-1.0.0 rebuilt.tar.gz"
    expect_rc 5 "install --dry-run with a version conflict" || return 1
    R --config "$CONF" --dry-run install "$PKGS/bad sum.tar.gz"
    expect_rc 4 "install --dry-run with a wrong checksum" || return 1
    [ ! -e "$hook.env" ] || { echo "install --dry-run ran the health check"; return 1; }
    rm -f "$SB/held"
    flock -x "$BASE/.relctl.lock" bash -c 'echo x >"$1"; sleep 3' _ "$SB/held" &
    holder=$!
    wait_file "$SB/held" 10 || { echo "the test could not take the lock"; return 1; }
    R --config "$CONF" --dry-run --lock-wait 0 install "$PKGS/app-1.1.0.tar.gz"
    wait "$holder"
    expect_rc 0 "install --dry-run while the lock is busy" || return 1
    [ "$(snapshot "$BASE")" = "$before" ] || { echo "--dry-run changed the base dir"; return 1; }
}

test_status() { # R3, R22, R25
    new_sandbox status
    write_conf "base_dir=$BASE"
    R --config "$CONF" status
    expect_rc 0 "status on a new base dir" || return 1
    [ "$(cat "$SB/out")" = "$(printf 'current=-\nprevious=-\nreleases=-')" ] ||
        { echo "status on a new base dir:"; cat "$SB/out"; return 1; }
    [ ! -e "$BASE" ] || { echo "status made the base dir"; return 1; }
    INSTALL_ARGS=(--config "$CONF")
    install_versions 1.0.0 1.10.0 1.9.0 || return 1
    R --config "$CONF" status
    expect_rc 0 "status" || return 1
    [ "$(cat "$SB/out")" = "$(printf 'current=1.9.0\nprevious=1.10.0\nreleases=1.0.0 1.9.0 1.10.0')" ] ||
        { echo "status output:"; cat "$SB/out"; return 1; }
}

test_permissions() { # R10
    new_sandbox perms
    write_conf "base_dir=$BASE" "health_cmd=/bin/true"
    make_pkg "$PKGS/app-1.0.0.tar.gz" 1.0.0
    (
        umask 000
        R --config "$CONF" install "$PKGS/app-1.0.0.tar.gz"
        echo "$RC" >"$SB/rc"
    )
    RC=$(cat "$SB/rc")
    expect_rc 0 "install with umask 000" || return 1
    local path want got
    for path in "|750" "releases|750" "history.tsv|640" "health.log|640"; do
        want=${path#*|}
        path=${path%|*}
        got=$(stat -c %a "$BASE/$path" 2>/dev/null)
        [ "$got" = "$want" ] || { echo "mode of '$path' is '$got', expected $want"; return 1; }
    done
}

test_stderr_format() { # R3
    local bad
    bad=$(grep -v '^relctl: \(info\|warn\|error\): .' "$STDERR_ALL" | head -n 5)
    [ -z "$bad" ] || { echo "stderr lines in another format:"; echo "$bad"; return 1; }
    [ -s "$STDERR_ALL" ] || { echo "no stderr was recorded"; return 1; }
    [ ! -s "$ERRLESS" ] || { echo "exits with a code that is not 0 and no error line:"; head -n 5 "$ERRLESS"; return 1; }
}

test_shellcheck() { # R26
    shellcheck "$SCRIPT"
}

if [ ! -f "$SCRIPT" ]; then
    echo "missing $SCRIPT"
fi

check usage_errors test_usage_errors
check install_basic test_install_basic
check config_parsing test_config_parsing
check config_errors test_config_errors
check precedence test_precedence
check package_checks test_package_checks
check same_version test_same_version
check shared_links test_shared_links
check health_check test_health_check
check health_failure test_health_failure
check health_timeout test_health_timeout
check lock test_lock
check signal_term test_signal_term
check signal_int test_signal_int
check rollback test_rollback
check prune test_prune
check dry_run test_dry_run
check status_output test_status
check permissions test_permissions
check stderr_format test_stderr_format
check shellcheck_clean test_shellcheck

write_result
exit 0
