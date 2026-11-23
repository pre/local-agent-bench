# Report and compare

## Report

```sh
just report ~/daybook-evidence/local-llm/eval/<run-id> [<run-id>...]
uv run llm-eval report <run-dir>... --out report.md
```

`report` reads `run.json` and each `*/result.json` of the run directories and writes Markdown to stdout or to the `--out` file. The report has these parts:

| Part | Content |
|---|---|
| Runs | Each run directory: trials found and expected, start and end time, and for a remote configuration the model IDs of the API responses (`reported_models` of `run.json`). A run that is not finished, or that has fewer results than tasks times repetitions, is marked PARTIAL |
| Configurations | One row for each configuration: trials counted, pass rate with a 95 % Wilson interval, passes of the tasks that are not hard (Base pass) and of the hard tasks (Hard pass), mean score, median and total wall time, cost, prompt and decode tokens per second, draft acceptance, GTT peak, lowest MemAvailable, lowest SwapFree, count of each failure reason, count of harness errors |
| Memory | One row for each configuration: GTT limit, GTT before start, GTT after load, GTT peak, Model GTT, GTT margin, lowest MemAvailable, lowest SwapFree, highest PSI full avg10. Then one line for each run that the memory guard stopped (`memory_guard` of `run.json`, see [Memory guard](server-control.md#memory-guard)), also for a run without trial results. A run without `memory_guard` gives no line |
| Tasks | Task against configuration: passes of the counted repetitions (for example `2/3`). The mean score is shown when a trial has a partial score |
| Failed trials | For each configuration: run, task, repetition, failure reason, score, failed check names, turns, wall time |
| Limits | The count of trials and the width of the interval for each configuration |
| Probes | The speed and protocol probe results, when the run directory has `probes/speed.json` or `probes/protocol.json` |

Rules:

- A configuration is a name and the SHA-256 of its values. The same name with a different SHA-256 is a different row, and the row label has the first 8 characters of the SHA-256.
- A trial with `harness_error` is not a model failure. It is not in the pass rate, the mean score and the median wall time. The total wall time includes it.
- Base pass and Hard pass are `passes/trials` of the counted trials, or `-` when the configuration has no trial of that kind. The report reads the `hard` value of each `result.json`, not the `tasks/` directory. A result of an older harness has no `hard` value: then a task ID that starts with `hard-` is a hard task.
- Rows are sorted by pass rate, then by median wall time.
- Speed values come from the `server` dictionary of `result.json`: the sum of the tokens divided by the sum of the seconds of all trials, not a mean of rates. Draft acceptance is the sum of accepted tokens divided by the sum of generated draft tokens.
- Memory values come from the `memory` dictionary of the trials and from `probes/memory.json`: the peak of the peaks and the minimum of the minimums. GTT peak also includes `gtt_used_load_peak_mib` of `run.json`. A value is `n/a` when no trial has it.
- All memory values are measured on the machine of the run. The report reads only the run files, not `/sys`, thus it can run later or on a different machine.
- In "Memory", GTT limit is `gtt_total_mib`, GTT before start is `gtt_used_before_start_mib` and GTT after load is `gtt_used_after_load_mib` of `run.json`. Model GTT is GTT peak minus GTT before start: the GTT of the server with its model and context. GTT margin is GTT limit minus GTT peak.
- A run without `gtt_used_after_load_mib` (an older run) gives GTT after load from `gtt_used_start_mib` of its first trial. A run without `gtt_total_mib` gives `n/a` for GTT limit and GTT margin. An external server gives `n/a` for GTT before start and Model GTT.
- Cost USD is the sum of `total_cost_usd` of all trials of a remote configuration, also of the harness errors (a trial without a value adds nothing). It is the estimate of Claude Code (see [Model and cost in the result](cloud-models.md#model-and-cost-in-the-result)). A local configuration gives `n/a`.
- A remote configuration gives `n/a` for all GTT values in "Configurations" and "Memory", because it does not use the local GPU memory. Another local server can run at the same time, and its GTT is not part of the result.
- When a row has more than one run, GTT limit and GTT peak are the maximum and GTT margin is the minimum of the runs. GTT before start and GTT after load come from the run with the highest GTT peak.

## Compare

```sh
just compare <run-dir-a> <run-dir-b>
```

`compare` pairs the tasks that both runs have. For each task it shows the passes and the mean score of A and B, and the difference. Then it shows the totals for the common tasks (pass rate with the 95 % interval, mean score, median wall time, decode tokens per second, harness errors) and the count of tasks where A is better, equal or worse. A task is better when its pass rate is higher. When the pass rates are equal, the mean score decides.

The "Noise" part tells if the difference is real:

- The 95 % Wilson intervals of the two pass rates overlap, or not.
- An exact two-sided sign test on the tasks that differ. With fewer than 6 tasks that differ, p cannot be below 0.05, and the output says so.

The result is "inside the noise" when the intervals overlap or p is 0.05 or more.

When a directory has no trial results (for example an empty directory, or a run that has only `run.json`), `compare` writes an error and the exit code is 2.
