#!/usr/bin/env bash
# Hidden check of the hard-go-sheet task.
# Replaces the tests of the engine package with the hidden tests, builds the
# test binary once and runs each hidden test as one check. The tests count
# the evaluations of formulas with a custom function, so they do not depend
# on the speed of the machine. One test has a time limit that is about 20
# times the time of the reference solution. The test binary runs with a
# limit of 4 GiB of virtual memory (the reference solution needs about
# 250 MiB), so that a solution that expands large ranges fails and does not
# use the memory of the host.
set -u

export GOCACHE=/tmp/verify-gocache
export GOPATH=/tmp/verify-gopath
export GOENV=off
export GOTELEMETRY=off
export GOTOOLCHAIN=local
export GOPROXY=off
export GOSUMDB=off
export GOFLAGS=-mod=mod

PKG=engine
TESTS=(
  TestBasics
  TestDiamondOnce
  TestLadderCounts
  TestConsistentReads
  TestCutoff
  TestSameValueNoEvaluation
  TestDynamicReads
  TestReadsOfEmptyCell
  TestApplyOneUpdate
  TestApplyAtomic
  TestCycleCheckUsesNewInputs
  TestWatchOrder
  TestWatchFinalValuesOnly
  TestRedefineFormula
  TestRangeReads
  TestDeepChain
  TestCostDoesNotGrowWithSheet
  TestWholeColumnRanges
  TestRangeErrorsAndOrder
)

out_dir=/out
log=$out_dir/verify.log
: >"$log"

names=()
results=()

add_check() {
  names+=("$1")
  results+=("$2")
}

write_result() {
  local total=${#names[@]} passed_count=0 items="" i
  for i in "${!names[@]}"; do
    [[ ${results[$i]} == true ]] && passed_count=$((passed_count + 1))
    items+="${items:+,}{\"name\":\"${names[$i]}\",\"passed\":${results[$i]}}"
  done
  local all=false
  ((total > 0 && passed_count == total)) && all=true
  local score
  score=$(awk -v p="$passed_count" -v t="$total" 'BEGIN { printf "%.4f", (t ? p / t : 0) }')
  printf '{"passed":%s,"score":%s,"checks":[%s]}\n' "$all" "$score" "$items" >"$out_dir/verify.json"
}

# The agent can add test files that collide with the hidden tests.
mkdir -p "/work/$PKG"
find "/work/$PKG" -maxdepth 1 -name '*_test.go' -delete
cp /verify/tests/$PKG/*_test.go "/work/$PKG/"

bin=/tmp/verify-bin/pkg.test
mkdir -p /tmp/verify-bin
built=false
if (cd /work && timeout 120 go test -c -o "$bin" "./$PKG") >>"$log" 2>&1; then
  built=true
fi
echo "build of the test binary: $built" >>"$log"

# The plan sheet of the prompt must finish.
plan_ok=false
if (cd /work && go build -o /tmp/verify-bin/sheetcalc ./cmd/sheetcalc && ulimit -v 4194304 && timeout 60 /tmp/verify-bin/sheetcalc -watch E1,E2,E3 /verify/tests/testdata/plan.sheet /verify/tests/testdata/plan.edits) >/tmp/verify-plan.txt 2>&1; then
  grep -q '^update 2: E1 114.332 -> 115.332$' /tmp/verify-plan.txt && plan_ok=true
fi
cat /tmp/verify-plan.txt >>"$log"

for t in "${TESTS[@]}"; do
  ok=false
  if $built; then
    test_out=$(cd "/work/$PKG" && ulimit -v 4194304 && timeout 60 "$bin" -test.run "^${t}\$" -test.v -test.count=1 -test.timeout=50s 2>&1)
    echo "$test_out" >>"$log"
    grep -q "^--- PASS: ${t} " <<<"$test_out" && ok=true
  fi
  add_check "$t" "$ok"
done
add_check plan_sheet_finishes "$plan_ok"

write_result
exit 0
