#!/usr/bin/env bash
# Hidden check of the hard-py-contactmig task: the migration CLI against the
# rules of docs/MIGRATION.md. The hidden tests build the v1 files at run time
# and read the result with the sqlite3 module of Python.
# The test functions run through "check" from lib.sh.
# shellcheck disable=SC2329
set -u
VERIFY_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
. "$VERIFY_DIR/lib.sh"

export PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp
unset PYTHONPATH CONTACTMIG_FAIL_AFTER_FILES
cd /work || exit 1

mkdir -p tests
cp "$VERIFY_DIR"/tests/*.py tests/

run_tests() {
    timeout 120 python3 -m unittest -v "$@"
}

hidden=tests.test_spec_hidden
check basic_migration run_tests "$hidden.BasicMigrationTest"
check decoding run_tests "$hidden.DecodingTest"
check lines_and_records run_tests "$hidden.LinesTest"
check normalization_and_field_errors run_tests "$hidden.NormalizationTest"
check name_limit run_tests "$hidden.NameLimitTest"
check merge_rules run_tests "$hidden.MergeTest"
check email_limit run_tests "$hidden.EmailLimitTest"
check file_order run_tests "$hidden.FileOrderTest"
check partial_failure run_tests "$hidden.PartialFailureTest"
check duplicate_ids run_tests "$hidden.DuplicateIdTest"
check repeat_runs run_tests "$hidden.RepeatRunTest"
check cross_run_merge run_tests "$hidden.CrossRunMergeTest"
check dry_run run_tests "$hidden.DryRunTest"
check resume_after_stop run_tests "$hidden.ResumeTest"
check cli_contract run_tests "$hidden.CliContractTest"
check present_tests run_tests tests.test_basic

write_result
exit 0
