# shellcheck shell=bash
# Shared helpers for verify.sh. Source this file, call check for each check,
# then call write_result. The result goes to $OUT_DIR/verify.json (default /out).

OUT_DIR=${OUT_DIR:-/out}
LOG_DIR=$(mktemp -d /tmp/verify-logs.XXXXXX)
check_names=()
check_results=()

# check NAME COMMAND [ARGS...]: run the command and record the result.
check() {
    local name=$1
    shift
    if "$@" >"$LOG_DIR/$name.log" 2>&1; then
        check_results+=(true)
        echo "PASS $name"
    else
        check_results+=(false)
        echo "FAIL $name"
        tail -n 40 "$LOG_DIR/$name.log" | sed 's/^/    /'
    fi
    check_names+=("$name")
}

write_result() {
    local total=${#check_names[@]} passed=0 i sep="" all=false score
    for i in "${!check_names[@]}"; do
        [ "${check_results[$i]}" = true ] && passed=$((passed + 1))
    done
    if [ "$total" -gt 0 ] && [ "$passed" -eq "$total" ]; then
        all=true
    fi
    score=$(awk -v p="$passed" -v t="$total" 'BEGIN { printf "%.4f", (t > 0 ? p / t : 0) }')
    {
        printf '{"passed": %s, "score": %s, "checks": [' "$all" "$score"
        for i in "${!check_names[@]}"; do
            printf '%s{"name": "%s", "passed": %s}' "$sep" "${check_names[$i]}" "${check_results[$i]}"
            sep=", "
        done
        printf ']}\n'
    } >"$OUT_DIR/verify.json"
    echo "passed=$all score=$score ($passed/$total)"
}
