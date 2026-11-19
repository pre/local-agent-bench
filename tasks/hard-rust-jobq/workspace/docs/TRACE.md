# Traces and replay

A trace is a recording of the calls that a client made to the scheduler. `jobq replay <file>` runs a trace against a new scheduler and prints a log. The replay is deterministic: the same trace gives the same log.

## Trace format

One command on each line. `#` starts a comment. Blank lines are ignored.

```
policy base=1000 max=3600000          # optional, before the first command
<time> submit <name> [delay=<ms>] [attempts=<n>] [script=<outcomes>]
<time> cancel <name>
<time> reschedule <name> delay=<ms>
<time> advance
```

- `<time>` is in milliseconds. The times of the lines must not decrease.
- `submit`: the defaults are `delay=0`, `attempts=3` and an empty script.
- `script` gives the outcome of each attempt of the job, in order: `done`, `retry` or `fatal`, separated by commas. `retry*3` is `retry,retry,retry`. An attempt after the end of the script gives `done`.

## Replay

For each line, the replay first calls `advance(<time>)` and then runs the command of the line.

- `submit` calls `Scheduler::submit`. If the submit is accepted, the replay keeps the id for the name (it replaces the id of an earlier job with that name) and uses the script of this line for the job.
- `cancel` and `reschedule` use the id that the replay kept for the name, as a client does that keeps the ids that it got. They do not use `lookup`. A name that was never submitted successfully gives `unknown`.
- The handler gives the outcome of the script of the job for the attempt number.

## Log

| Line | When |
|---|---|
| `t=<now> run <name>#<attempt> <outcome>` | `Event::Ran` |
| `t=<now> retry <name> at t=<due>` | `Event::RetryAt` |
| `t=<now> give up <name> after <n> attempts` | `Event::GaveUp` |
| `t=<time> submit <name> due t=<due>` | accepted submit |
| `t=<time> submit <name>: duplicate` | rejected submit (also `no attempts`, `time overflow`) |
| `t=<time> cancel <name>: ok` | also `not found`, `unknown` |
| `t=<time> reschedule <name>: due t=<due>` | also `not found`, `time overflow`, `unknown` |
| `end t=<now> pending=<n> submitted=... fatal=<n>` | last line: the clock and the counters |
| `pending: <name> <name> ...` | after the last line, when jobs are pending: `pending_names()` |
