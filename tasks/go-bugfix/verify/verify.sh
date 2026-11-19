#!/usr/bin/env bash
# Hidden check of go-bugfix. Runs in /work, writes /out/verify.json.
set -uo pipefail

export GOCACHE=/tmp/verify-go/cache GOPATH=/tmp/verify-go/path GOMODCACHE=/tmp/verify-go/mod
export GOPROXY=off GOFLAGS=-buildvcs=false GOTOOLCHAIN=local
log=/out/verify.log
: >"$log"

# The agent can change the tests in the workspace. Use only the hidden tests.
find /work -name '*_test.go' -not -path '*/.git/*' -delete
cp -r /verify/tests/. /work/

checks=()
record() { # name, then the command of the check
    local name=$1 passed=false
    shift
    echo "== $name: $*" >>"$log"
    if "$@" >>"$log" 2>&1; then
        passed=true
    fi
    checks+=("$(jq -cn --arg n "$name" --argjson p "$passed" '{name: $n, passed: $p}')")
}

hidden_test() { go test -count=1 -run "^$1\$" ./duration; }

cli_is() { # expected output, then the arguments of dur
    local want=$1
    shift
    [ "$(/tmp/verify-go/dur "$@")" = "$want" ]
}

cli_checks() {
    go build -o /tmp/verify-go/dur ./cmd/dur &&
        cli_is 1w2d12h 1w2d 12h &&
        cli_is 2h 1.05h 57m &&
        cli_is 2h15m 1h30m 45m &&
        ! /tmp/verify-go/dur 1d1w
}

record build go build ./...
record basic hidden_test TestHiddenBasic
record fraction hidden_test TestHiddenFraction
record order hidden_test TestHiddenOrder
record order_errors hidden_test TestHiddenOrderErrors
record format hidden_test TestHiddenFormat
record round_trip hidden_test TestHiddenRoundTrip
record cli cli_checks

printf '%s\n' "${checks[@]}" | jq -s '{
    passed: all(.[]; .passed),
    score: ((map(select(.passed)) | length) / length),
    checks: .
}' >/out/verify.json
