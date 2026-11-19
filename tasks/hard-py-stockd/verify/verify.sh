#!/usr/bin/env bash
# Hidden check of the hard-py-stockd task: restarts at any point must give the
# same results and the same state as one run, through the command line only.
# The test functions run through "check" from lib.sh.
# shellcheck disable=SC2329
set -u
VERIFY_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
. "$VERIFY_DIR/lib.sh"

export PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH
cd /work || exit 1

unit_tests() {
    timeout 120 python3 -m unittest
}

# The suite of the workspace first, before the hidden files are in tests/.
check unit_tests_pass unit_tests

mkdir -p tests
touch tests/__init__.py
cp "$VERIFY_DIR"/tests/test_hidden_restart.py "$VERIFY_DIR"/tests/golden.json \
    "$VERIFY_DIR"/tests/test_cli.py "$VERIFY_DIR"/tests/helpers.py tests/

run_tests() {
    timeout 120 python3 -m unittest -v "$@"
}

H=tests.test_hidden_restart
check cli_formats_unchanged run_tests tests.test_cli
check restart_multi_event_commands run_tests "$H.MultiEventCommandTest"
check reservation_after_restart run_tests "$H.ReservationAfterRestartTest"
check retry_after_restart run_tests "$H.RetryAfterRestartTest"
check retry_window_after_restart run_tests "$H.RetryWindowTest"
check non_ascii_large_segments run_tests "$H.NonAsciiTest"
check restart_mixed_random run_tests "$H.MixedRandomTest"
check compact_between_restarts run_tests "$H.CompactionTest"
check replay_equals_recovery run_tests "$H.ReplayTest"
check old_data_directory_loads run_tests "$H.OldDataDirectoryTest"

write_result
exit 0
