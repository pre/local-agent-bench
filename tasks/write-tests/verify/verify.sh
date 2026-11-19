#!/usr/bin/env bash
# Hidden check of the write-tests task.
# Takes the test files that the agent wrote in window/, runs them against the
# original window.go, and then against each mutant in /verify/mutants. Each
# mutant is one check. A mutant is killed when the tests fail on it. If the
# tests do not pass on the original code, no mutant counts as killed.
set -u

export GOCACHE=/tmp/verify-gocache
export GOPATH=/tmp/verify-gopath
export GOENV=off
export GOTELEMETRY=off
export GOTOOLCHAIN=local
export GOPROXY=off
export GOSUMDB=off
export GOFLAGS=-mod=mod

PKG=window

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

# Build a scratch module: the original code of the package and of the
# module file, and the test files of the agent (with their testdata).
scratch=/tmp/verify-module
rm -rf "$scratch"
mkdir -p "$scratch/$PKG"
cp -r /verify/original/. "$scratch/"
test_count=0
if [[ -d /work/$PKG ]]; then
  for f in /work/$PKG/*_test.go; do
    [[ -f $f ]] || continue
    cp "$f" "$scratch/$PKG/"
    test_count=$((test_count + 1))
  done
  [[ -d /work/$PKG/testdata ]] && cp -r "/work/$PKG/testdata" "$scratch/$PKG/"
fi
echo "test files of the agent: $test_count" >>"$log"

run_tests() {
  (cd "$scratch" && timeout 120 go test -count=1 -timeout 60s "./$PKG") >>"$log" 2>&1
}

original_ok=false
if ((test_count > 0)); then
  echo "=== original" >>"$log"
  run_tests && original_ok=true
fi
echo "tests pass on the original code: $original_ok" >>"$log"

for mutant in /verify/mutants/*.go; do
  name=$(basename "$mutant" .go)
  killed=false
  if $original_ok; then
    cp "$mutant" "$scratch/$PKG/window.go"
    echo "=== mutant $name" >>"$log"
    run_tests || killed=true
    echo "killed: $killed" >>"$log"
  fi
  add_check "mutant-$name" "$killed"
done
cp /verify/original/$PKG/window.go "$scratch/$PKG/window.go"

write_result
exit 0
