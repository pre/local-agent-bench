# The memory guard stops the main thread with a signal

Status: accepted.

When the memory guard trips, the main thread must stop at once and do the cleanup of a stop signal. But the main thread can wait a long time in a blocking call: a probe request waits up to 1800 s, and the wait for the agent container lasts up to the time limit of the task. Thus the guard thread sends SIGUSR1 to the main thread, and the handler raises `GuardStop`, which goes through the same cleanup as `KeyboardInterrupt`.

## Decision

- `stop.py` handles SIGUSR1 with the handler of the stop signals. The defer blocks (`defer_stop_signals`) also defer it, and a stop signal in the same block wins.
- `GuardStop` is a `BaseException`, the same as `KeyboardInterrupt`. Thus it goes through each `except Exception`. In `execute_run` such a handler writes a `harness_error` result.json, and `--resume` does not run a trial that has a result.json.
- The guard sends the signal before it kills the server. Thus the main thread stops before a probe or the agent sees a closed connection.
- The guard thread kills the server itself (`podman kill -s KILL`). The kill does not wait for the main thread, also when the main thread is in a defer block.
- A `GuardStop` starts a defer state that ends at `end_guard_stop()` in `run_plan`. A stop signal during the cleanup does not interrupt the cleanup. After the cleanup it stops the full run.

## Considered Options

- `_thread.interrupt_main()`: the handler runs only when the main thread runs Python code again. It does not stop a blocking system call, for example a probe request that waits for an answer.
- A flag that the main thread reads: the main thread reads it only between its blocking calls. Thus the stop can come 1800 s late.
- Only the kill, with no signal to the main thread: the probe or the agent sees the closed connection first. The probe records a failed case, and the trial in progress can get a `result.json` with a failure that is not a failure of the model.

## Consequences

- A new cleanup in the main thread that catches `KeyboardInterrupt` must also catch `GuardStop`. If not, a trip skips that cleanup.
- SIGUSR1 has no other use in the harness. The harness sets its handler also when SIGUSR1 was ignored at the start.
- A test must send the real guard signal through the handler of `stop_on_signals`. A test that raises `GuardStop` directly does not start the defer state, thus it does not test the cleanup of a trip.
