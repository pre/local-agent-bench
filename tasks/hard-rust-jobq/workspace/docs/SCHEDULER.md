# Scheduler

`jobq::Scheduler` runs jobs at given times and retries failed attempts with exponential backoff. It has a manual clock: the time is in milliseconds, starts at 0 and moves only in `advance`.

## Jobs and ids

- `submit(spec)` adds a job. Its first attempt is due at `now + spec.delay_ms`. It gives a `JobId`.
- A job is pending from its submit until it finishes or is cancelled. A job finishes when an attempt gives `Done`, when an attempt gives `Fatal`, or when its last permitted attempt gives `Retry` (the scheduler gives up).
- Two pending jobs cannot have the same name: `submit` gives `SchedError::Duplicate`. When a job is no longer pending, its name is free at once, and a new `submit` with that name is accepted.
- A `JobId` refers to one job only. When that job is no longer pending, each operation with the id has no effect: `cancel` and `reschedule` give `SchedError::NotFound`, and `due` gives `None`. This is also true after more jobs were submitted: a new job never gets an id that is equal to the id of an earlier job.
- `lookup(name)` gives the id of the pending job with that name, or `None`.
- `pending()` is the number of pending jobs.

## Order of attempts

The scheduler puts a job in its queue at `submit`, at `reschedule` and at each retry. Each time, the job gets a new sequence number from a counter of the scheduler (0, 1, 2, ...). Attempts run in the order of their due time. Attempts with the same due time run in the order of their sequence numbers.

`cancel(id)` removes the job from the queue. The order of all other attempts does not change.

`reschedule(id, delay_ms)` moves the next attempt of a pending job to `now + delay_ms` and gives the job a new sequence number.

`pending_names()` gives the names of the pending jobs in the order in which their next attempts will run.

## advance

`advance(to, handler)` runs each attempt that is due at or before `to`, in queue order, also the retries that become due at or before `to` during this call. Before each attempt the clock moves to the due time of the attempt (the clock never moves back). The handler gets a `JobInfo` with the attempt number (1 for the first attempt) and gives an `Outcome`. At the end the clock is `max(now, to)`.

After an attempt with number `n`:

| Outcome | Condition | Result |
|---|---|---|
| `Done` | | The job finishes |
| `Fatal` | | The job finishes. There is no retry |
| `Retry` | `n < max_attempts` | The next attempt is due at `now + policy.delay(n)`. Event `RetryAt` |
| `Retry` | `n == max_attempts` | The job finishes. Event `GaveUp` |

`advance` gives the events in the order in which they happened: `Ran` for each attempt, followed by `RetryAt` or `GaveUp` when it applies.

## Retries

`RetryPolicy { base_ms, max_ms }`. The default is `base_ms = 1000`, `max_ms = 3600000` (one hour).

`delay(n)` is the delay after the failed attempt `n`: `base_ms * 2^(n - 1)`. When this value is larger than `max_ms`, the delay is `max_ms`. This applies to every `n`, also when the exact value of `base_ms * 2^(n - 1)` does not fit in 64 bits. `delay(0)` is equal to `delay(1)`. Thus the delays of one job never decrease from one attempt to the next.

## Errors

| Error | When |
|---|---|
| `Duplicate(name)` | `submit` with the name of a pending job |
| `NotFound` | `cancel` or `reschedule` with an id of a job that is not pending |
| `NoAttempts` | `submit` with `max_attempts == 0` |
| `TimeOverflow` | `submit` or `reschedule` when `now + delay_ms` does not fit in 64 bits |

An operation that gives an error changes nothing.

## Counters

`stats()` gives counters since the scheduler was made: `submitted` (accepted submits), `cancelled` (successful cancels), `attempts` (handler calls), `done`, `retries` (`RetryAt` events), `gave_up` (`GaveUp` events) and `fatal` (attempts that gave `Fatal`).
