# Server control

A managed run does these steps:

1. Check that the model files (all parts of a split GGUF file), the draft model and the chat template exist.
2. If a container `llm-eval-server` exists: if it has the label `llm-eval.role=server`, it remains from an earlier run of the harness. The harness stops with a message, and `--replace` removes the old container. The harness never stops or removes a container without this label.
3. Read GTT used (`/sys/class/drm/card*/device/mem_info_gtt_used`). If it is more than `gtt_max_used_mib`, the harness stops with a message that lists the running containers. The harness does not stop other containers. A full GTT can stop the desktop.
4. Start `llm-eval-server`: `podman run -d --label llm-eval.role=server --runtime crun --device /dev/kfd --device /dev/dri/renderD128 --group-add keep-groups --security-opt seccomp=unconfined -p 127.0.0.1:<port>:8080`, the models directory read-only at `/models`, the API key file at `/run/api-key`, the chat template at `/run/chat-template.jinja`.
5. Wait until `/health` gives HTTP 200 (limit `start_timeout_s`). If the container stops, the harness shows the end of its log. The harness also reads GTT used each 0.2 s, because a model can load about 3 GiB of GTT each second. If GTT total (`mem_info_gtt_total`) minus GTT used is less than `gtt_min_margin_mib` (default 4096), the harness kills the container at once (`podman kill -s KILL`), then saves its log and removes it as in step 8, and stops the run of this configuration with a message that gives the two values. Thus a model that is too large fails its start and does not fill GTT and stop the desktop.
6. Start the memory guard (see [Memory guard](#memory-guard)).
7. Run the probes and the trials. Before each trial the harness checks `/health`. If the server is down, the run of this configuration stops (continue it later with `--resume`).
8. Stop the memory guard. Stop the container (`podman stop -t 60`), save its full log as `server.log` in the run directory, remove the container. The harness also does this step when a trial raises an error, when the harness gets a stop signal (see "Stop a run" in [README.md](../README.md#stop-a-run)) and when the memory guard trips.

`run.json` gets `server` with the values that make the result reproducible: `llama_server_args` (the full argument list), `podman_args`, `image` and `image_digest`, `llama_server_version` (the build line of `llama-server --version`, because the log does not show it at the default verbosity), `model_files` and `draft_model_files` (name and size of each part), `chat_template` (path and SHA-256) and `load_seconds` (from the start of the container to the first healthy `/health`). It also gets the GTT values of the start, in MiB:

- `gtt_used_before_start_mib`: GTT used before the start, that is, the GTT of the other programs.
- `gtt_used_after_load_mib`: GTT used after the first healthy `/health`.
- `gtt_used_load_peak_mib`: the highest GTT used during the wait for `/health` (one reading each 0.2 s).
- `gtt_total_mib`: GTT total, the limit of the kernel.

For an external server, `server` has the mode, the URL, the container and `gtt_total_mib`. The harness does not see the start of an external server, thus it has no other GTT values. A remote endpoint has no GTT values.

## Memory guard

The check of step 5 does not see the memory that the server gets after its start, for example when the KV cache becomes larger, and the memory of the agent and check containers. Thus a thread of the harness, the memory guard, reads the memory each second from the first healthy `/health` until the harness stops the server: during the probes, during each trial and between the trials. It reads GTT used and GTT total (`mem_info_gtt_used` and `mem_info_gtt_total`) and MemAvailable of `/proc/meminfo`. The guard trips when one of these conditions is true:

| Condition | Key | Default | `reason` |
|---|---|---|---|
| GTT total minus GTT used is less than the key | `gtt_min_margin_mib` | 4096 | `gtt_margin` |
| MemAvailable is less than the key | `mem_available_min_mib` | 2048. The value 0 switches off this condition | `mem_available` |

The check of step 5 uses the same `gtt_min_margin_mib`. The default 2048 of `mem_available_min_mib` is a chosen value, not a measured limit. The lowest MemAvailable that the harness measured in a real run was 14.8 GiB.

The guard reads the memory of the full host. Thus another program that fills the memory also trips it. The guard stops only the server of the harness, never another program.

When the guard trips, it:

1. Sends SIGUSR1 to the main thread of the harness. The main thread stops what it does, also a wait for the agent container or a probe request. The reason for a signal: [ADR 0003](adr/0003-memory-guard-stops-the-main-thread-with-a-signal.md).
2. Kills the server container at once (`podman kill -s KILL llm-eval-server`). The kill does not wait for the main thread. Thus the server stops about 1 to 2 s after the memory became low: up to 1 s until the next reading, then the time of the kill.
3. Writes the condition and its values to stderr and `run.log`, for example `llm-eval: MEMORY GUARD: GTT used is 109000 MiB of 112640 MiB, less free than server.gtt_min_margin_mib = 4096 MiB (trial go-bugfix-r2). The harness killed llm-eval-server.`

Then the harness does the cleanup of a stop signal: it removes the agent container of the running trial, saves `server.log` and removes the server container (see "Stop a run" in [README.md](../README.md#stop-a-run)). The trial in progress gets no `result.json`. Thus it is not a model failure, and `--resume` runs it again. The trials that did not start do not run. The harness writes `memory_guard` to `run.json` and this line to stderr and `run.log`:

```
llm-eval: <configuration>: the memory guard stopped the run of this configuration. The trial in progress has no result. To continue: llm-eval run --resume <run-dir>
```

Then the harness continues with the next configuration of `--config a --config b`, the same as after a server error. The exit code is 3 (see [Exit codes](runs.md#exit-codes)). After a trip, do the checks after a stop in "Stop a run" of [README.md](../README.md#stop-a-run).

`memory_guard` in `run.json`:

```json
{"reason": "gtt_margin", "limit_mib": 4096, "gtt_used_mib": 109000, "gtt_total_mib": 112640,
 "mem_available_mib": 20480, "phase": "trial go-bugfix-r2", "time": "2026-11-24T02:14:07+00:00"}
```

- `reason` and `limit_mib`: the condition and the value of its key.
- `gtt_used_mib`, `gtt_total_mib`, `mem_available_mib`: the values at the trip. `null` for a value that the guard could not read.
- `phase`: `start` (the server is healthy, the probes or the trials did not start), `probes`, `trial <task>-r<rep>` (from the start of the trial to its `result.json`) or `between trials` (also before the first trial and after the last trial).
- `time`: UTC.

`--resume` keeps `memory_guard`. A new trip replaces it. A trip before `run.json` exists (just after the first healthy `/health`) has only the message in `run.log`, and the last line tells how to start the run again. `llm-eval report` shows each trip in "Memory".

Other rules:

- When the guard cannot read a value (for example an error of sysfs), that value does not trip it. The other values still do. The first such error gives one warning in `run.log` and on stderr.
- A stop signal during the cleanup of a trip does not interrupt the cleanup, the same as a second stop signal. After the cleanup and the line above, it stops the full run: the exit code is 130 and the next configuration does not start. A trip during the cleanup of a stop signal kills the server, and the stop continues. In the two cases `run.json` gets `memory_guard`.
- An external or remote server has no guard: the harness did not start it and does not stop it.
