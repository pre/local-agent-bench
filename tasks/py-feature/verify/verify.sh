#!/usr/bin/env bash
# Hidden check of the py-feature task: the "capacity" subcommand of nodeinv.
set -u
VERIFY_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
. "$VERIFY_DIR/lib.sh"

export PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH
cd /work || exit 1

mkdir -p tests
cp "$VERIFY_DIR"/tests/*.py tests/

run_tests() {
    timeout 60 python3 -m unittest -v "$@"
}

check capacity_function run_tests tests.test_capacity.SummarizeFunctionTest
check capacity_table run_tests tests.test_capacity.CapacityTableTest
check capacity_json run_tests tests.test_capacity.CapacityJsonTest
check capacity_filters run_tests tests.test_capacity.CapacityFilterTest
check capacity_bad_attribute run_tests tests.test_capacity.CapacityErrorTest
check python_m_entry run_tests tests.test_capacity.ModuleEntryTest
check list_show_unchanged run_tests tests.test_cli tests.test_inventory

write_result
exit 0
