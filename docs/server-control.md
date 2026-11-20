# Server control

A managed run does these steps:

1. Check that the model files (all parts of a split GGUF file), the draft model and the chat template exist.
2. If a container `llm-eval-server` exists: if it has the label `llm-eval.role=server`, it remains from an earlier run of the harness. The harness stops with a message, and `--replace` removes the old container. The harness never stops or removes a container without this label.
3. Read GTT used (`/sys/class/drm/card*/device/mem_info_gtt_used`). If it is more than `gtt_max_used_mib`, the harness stops with a message that lists the running containers. The harness does not stop other containers. A full GTT can stop the desktop.
4. Start `llm-eval-server`: `podman run -d --label llm-eval.role=server --runtime crun --device /dev/kfd --device /dev/dri/renderD128 --group-add keep-groups --security-opt seccomp=unconfined -p 127.0.0.1:<port>:8080`, the models directory read-only at `/models`, the API key file at `/run/api-key`, the chat template at `/run/chat-template.jinja`.
5. Wait until `/health` gives HTTP 200 (limit `start_timeout_s`). If the container stops, the harness shows the end of its log. The harness also reads GTT used each 0.2 s, because a model can load about 3 GiB of GTT each second. If GTT total (`mem_info_gtt_total`) minus GTT used is less than `gtt_min_margin_mib` (default 4096), the harness kills the container at once (`podman kill -s KILL`), then saves its log and removes it as in step 7, and stops the run of this configuration with a message that gives the two values. Thus a model that is too large fails its start and does not fill GTT and stop the desktop.
6. Run the trials. Before each trial the harness checks `/health`. If the server is down, the run of this configuration stops (continue it later with `--resume`).
7. Stop the container (`podman stop -t 60`), save its full log as `server.log` in the run directory, remove the container. The harness also does this step when a trial raises an error or when the harness gets a stop signal (see "Stop a run" in [README.md](../README.md#stop-a-run)).

`run.json` gets `server` with the values that make the result reproducible: `llama_server_args` (the full argument list), `podman_args`, `image` and `image_digest`, `llama_server_version` (the build line of `llama-server --version`, because the log does not show it at the default verbosity), `model_files` and `draft_model_files` (name and size of each part), `chat_template` (path and SHA-256) and `load_seconds` (from the start of the container to the first healthy `/health`). It also gets the GTT values of the start, in MiB:

- `gtt_used_before_start_mib`: GTT used before the start, that is, the GTT of the other programs.
- `gtt_used_after_load_mib`: GTT used after the first healthy `/health`.
- `gtt_used_load_peak_mib`: the highest GTT used during the wait for `/health` (one reading each 0.2 s).
- `gtt_total_mib`: GTT total, the limit of the kernel.

For an external server, `server` has the mode, the URL, the container and `gtt_total_mib`. The harness does not see the start of an external server, thus it has no other GTT values. A remote endpoint has no GTT values.
