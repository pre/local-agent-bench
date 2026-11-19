#!/usr/bin/env bash
# Hidden check of the rust-feature task.
# Copies the hidden integration tests into /work and runs them.
# Each hidden test is one check.
set -u

export CARGO_HOME=/tmp/verify-cargo-home
export CARGO_TARGET_DIR=/tmp/verify-target
export CARGO_NET_OFFLINE=true
export CARGO_TERM_COLOR=never

TESTS=(
  reads_nodes
  inventory_errors
  plain_bytes
  decimal_suffixes
  binary_suffixes
  fractions
  fractions_are_exact
  fractions_round_down
  invalid_text
  empty_text
  largest_values
  display_round_trip
  best_fit_by_memory
  memory_left_after_placement_decides
  exact_fit_is_a_candidate
  only_ready_nodes
  tie_on_memory_uses_cpu_then_name
  overcommitted_node_has_no_room
  no_candidate
  returns_reference_into_slice
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

mkdir -p /work/tests
cp /verify/tests/inventory.rs /verify/tests/quantity.rs /verify/tests/place.rs /work/tests/

test_out=/tmp/verify-test-output.txt
(cd /work && timeout 180 cargo test --offline --no-fail-fast --test inventory --test quantity --test place -- --test-threads=4) >"$test_out" 2>&1
echo "cargo test exit code: $?" >>"$log"
cat "$test_out" >>"$log"

for t in "${TESTS[@]}"; do
  if grep -qx "test $t \.\.\. ok" "$test_out"; then
    add_check "$t" true
  else
    add_check "$t" false
  fi
done

write_result
exit 0
