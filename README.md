# llm-eval

Evaluation harness for a local LLM application: Claude Code (headless, `claude -p`) connected to a local inference server. The harness gives one comparable result for each configuration (model, server flags, client settings).

On the host only podman and the orchestrator (`uv run llm-eval`) run. The agent and the hidden check run in containers.

## Use

```sh
just image                                      # build localhost/llm-eval-agent:latest
just selfcheck                                  # check all tasks without an LLM
just run configs/qwen38-external.toml --task go-bugfix
just run configs/qwen38-external.toml --reps 3 --out ~/daybook-evidence/local-llm/eval/my-run
just run configs/qwen38-base.toml --tier quick  # the harness starts and stops the server
just run configs/qwen38-base.toml --config configs/qwen38-kv-f16.toml --tier full
just run configs/qwen38-27b.toml --tier quick --probe all  # probes first, no trials on a broken template
just download-model gpt-oss-120b                # download model files (see docs/models.md)
just resume ~/daybook-evidence/local-llm/eval/<run-id>
just report ~/daybook-evidence/local-llm/eval/<run-id>
just compare <run-dir-a> <run-dir-b>
just test                                       # unit tests with coverage
```

The justfile sets `TMPDIR` (default `~/tmp`) and the CA variables (`SSL_CERT_FILE` and others) to `/etc/ssl/certs/ca-certificates.crt`.

## Parts

| Part | Content |
|---|---|
| `image/Containerfile` | Agent image: Claude Code, Go 1.27 with gcc, Rust stable, Python 3.13, git, jq, yq 4, ripgrep, shellcheck, socat |
| `client-config/` | The Claude Code configuration directory of a trial. No `CLAUDE.md`, no plugins, no MCP servers. Each trial gets a new copy |
| `configs/` | One TOML file for each configuration (see [docs/configuration.md](docs/configuration.md)) |
| `templates/` | Chat templates that a managed configuration can name: `qwen38-flash-next.jinja` (Qwen3.8, accepts a system message after the first message) and `gpt-oss-120b.jinja` (the embedded gpt-oss-120b template, keeps a system message after the first message, see [docs/models.md](docs/models.md)) |
| `download/` | The list of model files (`models.tsv`) and the download script (see [docs/models.md](docs/models.md)) |
| `tasks/<task-id>/` | One task (see [docs/tasks.md](docs/tasks.md)) |
| `src/llm_eval/` | The orchestrator. Standard library only |
| `tests/` | Unit tests with fakes for podman and the server |

## Stop a run

Each of these signals stops a run:

| Action | Signal |
|---|---|
| Ctrl-C in the terminal, or `tmux send-keys -t llm-eval C-c` | SIGINT to all processes of the terminal, also to `tee`. When the tmux pane then closes, tmux sends SIGHUP |
| `kill <PID>` of `uv run` or of `llm-eval` | SIGTERM. `uv run` (version 0.13.6) sends SIGTERM and SIGHUP to the harness |
| The terminal closes, `tmux kill-session`, the SSH connection stops | SIGHUP |

At the first signal, the harness:

1. Stops and removes the agent container of the running trial (`podman rm -f -t 10 --ignore llm-eval-agent-...`), when a trial runs.
2. Stops the observers of the trial. The trial gets no `result.json`, thus `--resume` runs it again.
3. Stops `llm-eval-server` (`podman stop -t 60`), saves its log as `server.log` in the run directory and removes the container.
4. Writes `llm-eval: interrupted. To continue: llm-eval run --resume <run-dir>` and stops with exit code 130, also when `tee` stopped. When the stop came before the server was healthy, `run.json` does not exist and `--resume` does not work. Then the line is `llm-eval: interrupted. To start it again: llm-eval run --config <file> --out <run-dir> <the other options>`.

The same occurs during the server start, during the probes and during a trial. Some properties of the stop:

- One signal is sufficient. More SIGINT, SIGTERM or SIGHUP signals do not interrupt the cleanup. A second Ctrl-C does not stop it. The cleanup takes up to 60 s for the server and 10 s for the agent container. A signal during the normal stop of a server (at the end of a configuration) does not interrupt that stop either. The run then stops after it, and the next configuration of `--config a --config b` does not start.
- Python can lose the stop of a signal that arrives while Python deletes an object (the message "Exception ignored while calling deallocator ... KeyboardInterrupt"). Then the next signal stops the run. If `run.log` does not show `llm-eval: stopping llm-eval-server` after 15 s and `pgrep -af 'llm-eval run'` shows the harness, send `kill -TERM <PID>`.
- Only the main thread of the harness gets the signals. Thus a signal also stops a probe request at once, which can otherwise wait up to 1800 s.
- The podman commands of the cleanup run in a new process group. A signal of the terminal or of tmux does not stop them.
- The messages of the cleanup go to stderr and to `run.log` in the run directory. In `... 2>&1 | tee -a <log>`, Ctrl-C also stops `tee`. Then the messages are only in `run.log`, not in `<log>`. Use `tee -i -a <log>`: `tee` then ignores SIGINT, `<log>` also gets the messages, and the tmux pane stays open until the harness stops.
- `kill -KILL` stops the harness before its cleanup. Use it only when the harness does not stop in 2 minutes. Then do the manual cleanup below.
- When SIGHUP or SIGINT is ignored at the start (`nohup`, a background job of a shell script), the harness keeps it ignored.

After a stop, do these checks:

```sh
tail -n 3 <run-dir>/run.log   # "llm-eval-server is removed, its log is server.log" and the --resume line
ls -l <run-dir>/server.log
podman ps -a --filter label=llm-eval.role=server --format '{{.Names}} {{.Status}}'   # no line
podman ps -a --filter name=llm-eval-agent- --format '{{.Names}} {{.Status}}'         # no line
pgrep -af 'llm-eval run'      # no line
awk '{printf "%d MiB\n",$1/1048576}' /sys/class/drm/card*/device/mem_info_gtt_used   # GTT is free again
```

Manual cleanup, only when one of the checks shows a remaining container:

```sh
podman stop -t 60 llm-eval-server
podman logs llm-eval-server > <run-dir>/server.log 2>&1
grep -cF -f ~/.config/llama-server/api-key <run-dir>/server.log   # 0: the log does not contain the key
podman rm llm-eval-server
podman rm -f -t 10 <llm-eval-agent-... name>
```

Remove only containers with the name `llm-eval-server` (label `llm-eval.role=server`) or `llm-eval-agent-*`. Never remove other containers.

## Image

`just image` copies the Claude Code binary of the host (`~/.local/share/claude/versions/<version>`) into the image and checks it by SHA-256. `CLAUDE_VERSION` selects the version, default 2.1.328. The base images (`golang:1.27`, `rust`) are pinned by digest. The yq binary is pinned by version and SHA-256. The Debian packages (jq, ripgrep, shellcheck, socat) come from Debian 13 and can get security updates in a rebuild.

## Documentation

| File | Content |
|---|---|
| [docs/configuration.md](docs/configuration.md) | Configuration files, managed server, base and variants, what Claude Code sends to the server |
| [docs/models.md](docs/models.md) | The local models and their download |
| [docs/cloud-models.md](docs/cloud-models.md) | Claude models through the company LLM gateway: secrets, network of a remote endpoint, cost |
| [docs/network.md](docs/network.md) | Network isolation of the agent container |
| [docs/server-control.md](docs/server-control.md) | Start and stop of a managed server, GTT limits, server values in `run.json` |
| [docs/observers.md](docs/observers.md) | Memory and server observers during a trial |
| [docs/runs.md](docs/runs.md) | Tiers, repetitions, resume, trial procedure, result files, failure reasons |
| [docs/tasks.md](docs/tasks.md) | Task contract and how to add a task |
| [docs/report.md](docs/report.md) | The `report` and `compare` commands |
| [docs/probes.md](docs/probes.md) | Speed and protocol probes of a server |
