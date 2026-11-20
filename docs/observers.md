# Observers

The harness starts the observers just before the agent container and stops them just after it. Each one gives a key of `result.json`.

`memory` (always on): a thread of the harness reads the host memory each second and writes `memory.csv` in the trial directory with the columns `time` (UTC), `gtt_used_mib`, `mem_available_mib`, `swap_free_mib`, `psi_some_avg10`, `psi_full_avg10` (`/proc/pressure/memory`).

```json
{"gtt_used_start_mib": 91828, "gtt_used_peak_mib": 91934, "mem_available_min_mib": 16008,
 "swap_free_min_mib": 4053, "psi_some_avg10_max": 2.09, "psi_full_avg10_max": 1.94, "samples": 125}
```

`server` (on for a managed server, and for an external server with `container`): reads the log of the server container for the time of the trial (`podman logs --since`), saves it as `server.log` in the trial directory and adds the `print_timing` lines of llama-server. A rate is the total tokens divided by the total seconds of all requests. The draft values are `null` without a draft model. Without a container, `server` is `null`.

```json
{"requests": 25, "prompt_tokens": 90708, "prompt_seconds": 312.579, "prompt_tps": 290.19,
 "decode_tokens": 17894, "decode_seconds": 773.532, "decode_tps": 23.13,
 "draft_accepted": 11323, "draft_generated": 19642, "draft_acceptance": 0.5765}
```

The log has no client ID. If other clients use an external server during a trial, their requests are also in these values. A managed server has no other clients.
