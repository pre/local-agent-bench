#!/usr/bin/env bash
# Hidden check of the long-context task: addrplan/plan.py must agree with
# revision 14 of docs/network-standard.md, including the site deviations.
# The test functions run through "check" from lib.sh.
# shellcheck disable=SC2329
set -u
VERIFY_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib.sh
. "$VERIFY_DIR/lib.sh"

export PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH
cd /work || exit 1

STANDARD_SHA256=ef560b77e955074cb0b560c789305de9395addc1c42b288e90aa36fe1c546bbf

standard_unchanged() {
    [ "$(sha256sum docs/network-standard.md | cut -d' ' -f1)" = "$STANDARD_SHA256" ]
}

mkdir -p tests
cp "$VERIFY_DIR"/tests/*.py tests/

run_tests() {
    timeout 60 python3 -m unittest -v "$@"
}

check bmc_general_rule run_tests tests.test_plan.BmcGeneralTest
check bmc_withdrawn_tmp1_rule run_tests tests.test_plan.BmcTmp1Test
check bmc_hel2_hall_b run_tests tests.test_plan.Hel2HallBTest
check vlans run_tests tests.test_plan.VlanTest
check mtu_oul1_storage run_tests tests.test_plan.MtuTest
check node_plan_and_cli run_tests tests.test_plan.NodePlanTest
check unchanged_behaviour run_tests tests.test_plan.UnchangedBehaviourTest
check standard_revision run_tests tests.test_plan.RevisionTest
check standard_unchanged standard_unchanged

write_result
exit 0
