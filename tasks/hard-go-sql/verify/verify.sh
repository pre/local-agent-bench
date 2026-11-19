#!/usr/bin/env bash
# Hidden check of the hard-go-sql task.
# Replaces the tests of the db package with the hidden tests, builds the test
# binary once and runs each hidden test as one check. The hidden tests make
# their own table, so they do not depend on the files in testdata.
set -u

export GOCACHE=/tmp/verify-gocache
export GOPATH=/tmp/verify-gopath
export GOENV=off
export GOTELEMETRY=off
export GOTOOLCHAIN=local
export GOPROXY=off
export GOSUMDB=off
export GOFLAGS=-mod=mod

PKG=db
TESTS=(
  TestCountForms
  TestGroupOrderAfterWhere
  TestSumAvgTypes
  TestEmptyInput
  TestIdenticalValuesGroup
  TestExactIntegerSum
  TestGroupByItems
  TestGroupByErrors
  TestGroupingErrors
  TestAggregateMisuse
  TestHaving
  TestOrderByInAggregateQuery
  TestDistinct
  TestDistinctAggregates
  TestMinMaxAndNames
  TestVersionOneQueries
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

for t in "${TESTS[@]}"; do
  ok=false
  if $built; then
    test_out=$(cd "/work/$PKG" && timeout 60 "$bin" -test.run "^${t}\$" -test.v -test.count=1 -test.timeout=50s 2>&1)
    echo "$test_out" >>"$log"
    grep -q "^--- PASS: ${t} " <<<"$test_out" && ok=true
  fi
  add_check "$t" "$ok"
done

write_result
exit 0
