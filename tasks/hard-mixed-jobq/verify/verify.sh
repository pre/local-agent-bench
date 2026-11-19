#!/usr/bin/env bash
# Hidden check of the hard-mixed-jobq task: the version 2 contract in all parts.
# Builds the server, renders the manifests of both environments with the
# deploy script, then runs hidden Python tests: black-box tests of the server
# process, tests of the client against the real server, and a small kubelet
# that starts the server with the environment, the Secret files and the ports
# of the rendered Deployment.
# The test functions run through "check" from lib.sh.
# shellcheck disable=SC2329
set -u
VERIFY_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
. "$VERIFY_DIR/lib.sh"

export GOCACHE=/tmp/jobq-check/gocache
export GOPATH=/tmp/jobq-check/gopath
export GOENV=off
export GOTELEMETRY=off
export GOTOOLCHAIN=local
export GOPROXY=off
export GOSUMDB=off
export GOFLAGS=-mod=mod
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH JOBQ_URL JOBQ_TOKEN_FILE

CHECK_DIR=/tmp/jobq-check
export JOBQ_WORK=/work
export JOBQ_SERVER_BIN=$CHECK_DIR/jobq-server
export JOBQ_RENDERED_DIR=$CHECK_DIR/rendered
export JOBQ_CHECK_TOKEN=check-Token_2c81e5d04b
mkdir -p "$CHECK_DIR" "$JOBQ_RENDERED_DIR"
TOKEN_FILE=$CHECK_DIR/token.txt
printf '%s\n' "$JOBQ_CHECK_TOKEN" >"$TOKEN_FILE"

# The hidden tests run from a copy outside the workspace.
TESTS_DIR=$CHECK_DIR/tests
rm -rf "$TESTS_DIR"
cp -r "$VERIFY_DIR/tests" "$TESTS_DIR"

cd /work || exit 1

build_server() {
    (cd /work/service && timeout 120 go build -o "$JOBQ_SERVER_BIN" ./cmd/jobq-server)
}

go_tests() {
    (cd /work/service && timeout 90 go test -count=1 ./...)
}

client_tests() {
    (cd /work/client && timeout 60 env -u JOBQ_URL -u JOBQ_TOKEN_FILE python3 -m unittest discover -v)
}

render() {
    local env
    for env in staging production; do
        rm -rf "${JOBQ_RENDERED_DIR:?}/$env"
        timeout 60 bash /work/deploy/deploy.sh --env "$env" --token-file "$TOKEN_FILE" \
            --render-only "$JOBQ_RENDERED_DIR/$env" </dev/null || return 1
    done
}

# The check has a limit of 300 s. A slow or hanging server must not use all of
# it, so each test class gets at most 60 s and no class starts after 270 s.
CHECK_BUDGET_S=270

hidden() {
    [ -x "$JOBQ_SERVER_BIN" ] || { echo "the server was not built"; return 1; }
    local left=$((CHECK_BUDGET_S - SECONDS))
    [ "$left" -gt 5 ] || { echo "not run: the time limit of the check is used up"; return 1; }
    [ "$left" -lt 60 ] || left=60
    local rc=0
    (cd "$TESTS_DIR" && timeout -k 5 "$left" python3 -m unittest -v "$@") || rc=$?
    # A killed test run can leave a server that holds the ports.
    pkill -KILL -f "^$JOBQ_SERVER_BIN" 2>/dev/null
    return "$rc"
}

hidden_deploy() {
    [ -d "$JOBQ_RENDERED_DIR/staging" ] || { echo "the manifests were not rendered"; return 1; }
    hidden "$@"
}

check server_builds build_server
check go_tests_pass go_tests
check client_tests_pass client_tests
check shellcheck_deploy shellcheck /work/deploy/deploy.sh
check deploy_renders render

check server_refused_start hidden test_server.StartupTest
check server_default_ports hidden test_server.DefaultsTest
check server_routes hidden test_server.RoutesTest
check server_auth hidden test_server.AuthTest
check server_timeout hidden test_server.TimeoutTest
check server_pages hidden test_server.PagesTest
check server_errors hidden test_server.ErrorsTest
check server_drain hidden test_server.DrainTest
check server_metrics_listener hidden test_server.MetricsTest

check client_api hidden test_client_live.ClientApiTest
check client_pages hidden test_client_live.ClientPagesTest
check client_errors hidden test_client_live.ClientErrorsTest
check client_cli hidden test_client_live.CliTest

check deploy_secret_and_token_file hidden test_deploy.RenderTest
check pod_starts_ready hidden_deploy test_deploy.PodStartsTest
check service_reaches_api hidden_deploy test_deploy.ServiceTest
check metrics_scrape hidden_deploy test_deploy.MetricsScrapeTest
check networkpolicy_ports hidden_deploy test_deploy.NetworkPolicyTest
check token_mount hidden_deploy test_deploy.TokenMountTest
check config_from_configmap hidden_deploy test_deploy.ConfigTest
check drain_grace_period hidden_deploy test_deploy.GraceTest

write_result
exit 0
