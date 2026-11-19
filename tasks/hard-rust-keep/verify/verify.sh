#!/usr/bin/env bash
# Hidden check of the hard-rust-keep task.
# Copies the hidden integration test into /work and runs it.
# Each hidden test is one check.
set -u

export CARGO_HOME=/tmp/verify-cargo-home
export CARGO_TARGET_DIR=/tmp/verify-target
export CARGO_NET_OFFLINE=true
export CARGO_TERM_COLOR=never

TESTS=(
  empty_policy_is_an_error
  ties_use_the_id
  iso_weeks_at_year_ends
  buckets_use_the_policy_timezone
  hourly_with_a_half_hour_offset
  within_clamps_month_ends_and_leap_days
  within_hours_in_local_time
  within_daily_keeps_one_each_local_day
  zero_span_keeps_the_newest_time
  groups_by_tags_with_safety
  group_order_and_fields
  rules_are_independent_and_reasons_are_ordered
  counts_limit_the_buckets
  plan_structure
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
cp /verify/tests/hidden_plan.rs /work/tests/

test_out=/tmp/verify-test-output.txt
(cd /work && timeout 180 cargo test --offline --no-fail-fast --test hidden_plan -- --test-threads=4) >"$test_out" 2>&1
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
