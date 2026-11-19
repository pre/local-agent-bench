#!/usr/bin/env bash
# Hidden check of the hard-rust-jobq task.
# Copies the hidden integration tests and traces into /work/tests and runs
# them, with the visible integration tests. Each test is one check.
set -u

export CARGO_HOME=/tmp/verify-cargo-home
export CARGO_TARGET_DIR=/tmp/verify-target
export CARGO_NET_OFFLINE=true
export CARGO_TERM_COLOR=never

TESTS=(
  stale_id_cancel_is_not_found
  stale_id_reschedule_is_not_found
  ids_are_never_reused
  order_matches_the_specification
  pending_names_follow_the_queue
  backoff_is_exact_for_all_attempts
  long_retry_chain_waits_the_full_delay
  fatal_frees_the_name
  give_up_frees_the_name
  errors_change_nothing
  retry_gets_a_new_sequence_number
  replay_resubmit_uses_the_new_script
  replay_trace1
  replay_trace2
  replay_trace3
  runs_in_due_order
  retries_with_backoff
  cancel_and_reschedule
  duplicate_names
  time_does_not_go_back
  replay_small_trace
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

mkdir -p /work/tests/hidden
rm -f /work/tests/hidden/*
cp /verify/tests/hidden_scheduler.rs /verify/tests/hidden_replay.rs /work/tests/
cp /verify/tests/hidden/* /work/tests/hidden/
cp /verify/tests/scheduler.rs /work/tests/scheduler.rs

test_out=/tmp/verify-test-output.txt
(cd /work && timeout 240 cargo test --offline --release --no-fail-fast \
  --test hidden_scheduler --test hidden_replay --test scheduler -- --test-threads=4) >"$test_out" 2>&1
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
