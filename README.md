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
just resume ~/daybook-evidence/local-llm/eval/<run-id>
just test                                       # unit tests with coverage
```

`just image` copies the Claude Code binary of the host (`~/.local/share/claude/versions/<version>`) into the image. `CLAUDE_VERSION` selects the version, default 2.1.328.

The justfile sets `TMPDIR` (default `~/tmp`) and the CA variables (`SSL_CERT_FILE` and others) to `/etc/ssl/certs/ca-certificates.crt`.

## Parts

| Part | Content |
|---|---|
| `image/Containerfile` | Agent image: Claude Code, Go 1.27 with gcc, Rust stable, Python 3.13, git, jq, yq 4, ripgrep, shellcheck, socat. Base images pinned by digest |
| `client-config/` | The Claude Code configuration directory of a trial. No `CLAUDE.md`, no plugins, no MCP servers. Each trial gets a new copy |
| `configs/` | One TOML file for each configuration |
| `templates/` | Chat templates that a managed configuration can name |
| `tasks/<task-id>/` | One task (see "Task contract") |
| `src/llm_eval/` | The orchestrator. Standard library only |
| `tests/` | Unit tests with fakes for podman and the server |

## Configuration

```toml
name = "qwen38-external"             # default: the file name

[server]
mode = "external"                    # the server runs already, the harness does not start or stop it
url = "http://127.0.0.1:8080"        # URL on the host
api_key_file = "~/.config/llama-server/api-key"
model = "qwen3.8-flash-next"         # model ID for all Claude Code model variables
context_tokens = 131072              # CLAUDE_CODE_MAX_CONTEXT_TOKENS
health_path = "/health"              # optional, the harness checks it before the run
agent_network = "proxy"              # optional, see "Network"
# agent_url = "http://10.0.2.2:8080" # necessary when agent_network is not "proxy"

[client]
image = "localhost/llm-eval-agent:latest"
config_dir = "client-config"

[client.env]                         # more environment variables for Claude Code
CLAUDE_CODE_ATTRIBUTION_HEADER = "0"
```

`result.json` has the SHA-256 of the configuration values. An external server can also have `container = "llama-qwen38"`: the name of its podman container. Then the harness reads the speed values from its log (see "Observers").

### Managed server

With `mode = "managed"` the harness starts a `llama-server` container for the run (see "Server control"):

```toml
[server]
mode = "managed"
image = "docker.io/kyuz0/amd-strix-halo-toolboxes@sha256:a01d..."  # must be pinned by digest
models_dir = "~/models/qwen3.8-flash-next"   # mounted read-only at /models
model_file = "UD-Q4_K_XL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf"  # below models_dir
model = "qwen3.8-flash-next"                 # --alias, and the model ID for Claude Code
context_tokens = 131072                      # -c, and CLAUDE_CODE_MAX_CONTEXT_TOKENS
chat_template = "templates/qwen38-flash-next.jinja"  # optional, a file below templates/
api_key_file = "~/.config/llama-server/api-key"
port = 8090                                  # host port, on 127.0.0.1 only
gtt_max_used_mib = 12288                     # optional, see "Server control"
start_timeout_s = 900                        # optional, the time limit for /health
health_path = "/health"                      # optional
agent_network = "proxy"                      # optional, see "Network"

[server.args]                                # more llama-server flags
-ngl = 999
-lzm = "on"
--jinja = true                               # true: the flag alone. false: the harness does not give the flag
--temp = 1.0
--chat-template-kwargs = '{"reasoning_effort":"medium"}'

[server.draft]                               # optional draft model (for example an MTP head)
model_file = "MTP/mtp-Qwen3.8-Flash-Next-Q8_0.gguf"  # below models_dir. "" means no draft model
args = { --spec-type = "draft-mtp", --spec-draft-n-max = 3 }
```

The harness sets these flags itself, and they are not permitted in `args`: `--host 0.0.0.0 --port 8080 --api-key-file /run/api-key -m /models/<model_file> --alias <model> -c <context_tokens>`, `--chat-template-file /run/chat-template.jinja` (with `chat_template`) and `-md /models/<draft model_file>` (with a draft model). `args` is a table and not a list, so a variant file can change one flag.

### Base and variants

A configuration file can name a base file: `base = "qwen38-base.toml"` (the path is relative to the file). The file then holds only the values that it changes. Tables merge key by key, lists and scalars replace the value of the base. The `name` of the base is not inherited (default: the file name). The SHA-256 is of the merged values, so two files with the same merged values have the same SHA-256. A base file can have a base file.

```toml
# configs/qwen38-kv-f16.toml
base = "qwen38-base.toml"
name = "qwen38-kv-f16"

[server.args]
-ctk = "f16"
-ctv = "f16"
```

The configurations of the first matrix:

| File | Change from `qwen38-base.toml` |
|---|---|
| `qwen38-base.toml` | Managed. The settings of the server `llama-qwen38` (UD-Q4_K_XL, MTP head, context 131072, KV cache q8_0, temperature 1.0, reasoning effort xhigh of the template), port 8090 |
| `qwen38-effort-medium.toml` | `--chat-template-kwargs '{"reasoning_effort":"medium"}'` |
| `qwen38-effort-low.toml` | `--chat-template-kwargs '{"reasoning_effort":"low"}'` |
| `qwen38-iq4-xs.toml` | Quant UD-IQ4_XS |
| `qwen38-kv-f16.toml` | `-ctk f16 -ctv f16` |
| `qwen38-ctx-65536.toml` | `-c 65536`, and Claude Code gets the same value |
| `qwen38-no-mtp.toml` | No draft model |
| `qwen38-temp-0.6.toml` | `--temp 0.6` |
| `qwen38-external.toml` | External: the server `llama-qwen38` that runs already |

The chat template accepts only the reasoning effort values xhigh (the default, also for "high"), medium and low. Another value gives an error for each request.

## Network

`agent_network = "proxy"` (the default) is the most isolated mode. The agent container has no network (`--network=none`). The harness listens on a Unix socket and sends each connection to the server URL. In the container, socat listens on `127.0.0.1:8080` and sends each connection to that socket. Thus Claude Code reaches only the server: no internet, no DNS, no other host service.

The relay works for an external and for a managed server. Another value of `agent_network` goes to `podman run --network`, and `agent_url` is then the server URL in the container. These modes are less isolated. Examples:

- `container:llama-qwen38` with `agent_url = "http://127.0.0.1:8080"`: the agent uses the network namespace of the server container. The agent can also reach the internet through it.
- `slirp4netns:allow_host_loopback=true` with `agent_url = "http://10.0.2.2:8080"`: the agent can reach the internet and all services on the loopback interface of the host.

The check container always has no network.

## Server control

A managed run does these steps:

1. Check that the model files (all parts of a split GGUF file), the draft model and the chat template exist.
2. If a container `llm-eval-server` exists: if it has the label `llm-eval.role=server`, it remains from an earlier run of the harness. The harness stops with a message, and `--replace` removes the old container. The harness never stops or removes a container without this label.
3. Read GTT used (`/sys/class/drm/card*/device/mem_info_gtt_used`). If it is more than `gtt_max_used_mib`, the harness stops with a message that lists the running containers. The harness does not stop other containers. A full GTT can stop the desktop.
4. Start `llm-eval-server`: `podman run -d --label llm-eval.role=server --runtime crun --device /dev/kfd --device /dev/dri/renderD128 --group-add keep-groups --security-opt seccomp=unconfined -p 127.0.0.1:<port>:8080`, the models directory read-only at `/models`, the API key file at `/run/api-key`, the chat template at `/run/chat-template.jinja`.
5. Wait until `/health` gives HTTP 200 (limit `start_timeout_s`). If the container stops, the harness shows the end of its log.
6. Run the trials. Before each trial the harness checks `/health`. If the server is down, the run of this configuration stops (continue it later with `--resume`).
7. Stop the container (`podman stop -t 60`), save its full log as `server.log` in the run directory, remove the container. The harness also does this step when a trial raises an error or when you push Ctrl-C.

`run.json` gets `server` with the values that make the result reproducible: `llama_server_args` (the full argument list), `podman_args`, `image` and `image_digest`, `llama_server_version` (the build line of `llama-server --version`, because the log does not show it at the default verbosity), `model_files` and `draft_model_files` (name and size of each part), `chat_template` (path and SHA-256), `load_seconds` (from the start of the container to the first healthy `/health`) and `gtt_used_before_start_mib`. For an external server, `server` has the mode, the URL and the container.

## Observers

The harness starts the observers just before the agent container and stops them just after it. Each one gives a key of `result.json`.

`memory` (always on): a thread of the harness reads the host memory each second and writes `memory.csv` in the trial directory with the columns `time` (UTC), `gtt_used_mib`, `mem_available_mib`, `swap_free_mib`, `psi_some_avg10`, `psi_full_avg10` (`/proc/pressure/memory`).

```json
{"gtt_used_start_mib": 88021, "gtt_used_peak_mib": 88340, "mem_available_min_mib": 19650,
 "swap_free_min_mib": 4073, "psi_some_avg10_max": 0.0, "psi_full_avg10_max": 0.0, "samples": 812}
```

`server` (on for a managed server, and for an external server with `container`): reads the log of the server container for the time of the trial (`podman logs --since`), saves it as `server.log` in the trial directory and adds the `print_timing` lines of llama-server. A rate is the total tokens divided by the total seconds of all requests. The draft values are `null` without a draft model. Without a container, `server` is `null`.

```json
{"requests": 25, "prompt_tokens": 90708, "prompt_seconds": 312.579, "prompt_tps": 290.19,
 "decode_tokens": 17894, "decode_seconds": 773.532, "decode_tps": 23.13,
 "draft_accepted": 11323, "draft_generated": 19642, "draft_acceptance": 0.5765}
```

The log has no client ID. If other clients use an external server during a trial, their requests are also in these values. A managed server has no other clients.

## Tiers, repetitions and long runs

| Option | Tasks | Repetitions |
|---|---|---|
| `--tier quick` | Tasks with `quick = true` | 1 |
| `--tier full` | All tasks | 3 |
| No `--tier` | All tasks | 1 |

`--task` (can repeat) and `--reps` replace the values of the tier.

- `--config` can repeat. The configurations run one after the other, each with its own run directory and its own server: the harness stops server A before it starts server B. A server error stops only the run of that configuration, and the exit code is then 1. `--out` is permitted with one `--config` only.
- The selfcheck runs once for each agent image before the first configuration.
- An exception in a trial gives a `result.json` with `failure_reason = "harness_error"`, the error in `failure_detail` and the traceback in `harness_error.txt`. The run continues with the next trial.
- After each trial a progress line goes to stdout and to `run.log` in the run directory, for example `2026-11-19T18:20:01+00:00 [3/15] qwen38-base go-bugfix r3 FAIL verify_failed wall 878.2 s passed 1/3`.
- `run --resume <run-dir>` (or `just resume <run-dir>`) continues a run that stopped. It reads the configuration, the tasks and the repetitions from `run.json`, and stops if the configuration file changed. It does not run trials that have a `result.json` again, and it removes the directory of a trial without `result.json` before it runs that trial again. Also a `harness_error` trial has a `result.json`. To run it again, remove its directory first.
- After Ctrl-C the harness stops the server and shows the `--resume` command.

## Trial procedure

1. Copy `workspace/` to `<trial>/work` and make a git repository with one commit "chore: Start the task" (identity `eval <eval@localhost>`, fixed date, so the SHA is the same in each trial).
2. Copy `client-config/` to `<trial>/claude-config`.
3. Run the agent container: `claude -p <prompt.md> --output-format stream-json --verbose --max-turns <max_turns> --dangerously-skip-permissions`. Stop it at `timeout_s`.
4. Write the diff of the work against the start commit (new files included) in a container.
5. Run the check container: `bash /verify/verify.sh`, limit 300 s.
6. Write `result.json`. Then replace the API key with `<redacted>` in all files of the trial.

Containers:

| Container | Mounts | Network | Environment |
|---|---|---|---|
| Agent | `<trial>/work:/work`, `<trial>/claude-config:/claude-config`, relay directory at `/run/llm-eval` (proxy mode) | `none` (proxy mode) | `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` (from the key file, not in the podman arguments), `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_{FABLE,OPUS,SONNET,HAIKU}_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_MAX_CONTEXT_TOKENS`, `[client.env]` |
| Diff | `<trial>/work:/work` | `none` | `EVAL_BASELINE` |
| Check | `<trial>/work:/work`, `tasks/<id>/verify:/verify:ro`, `<trial>/check:/out` | `none` | `EVAL_BASELINE` |

All containers use `--userns=keep-id:uid=1000,gid=1000` and `--init`. The user in the container is `eval` (UID 1000, `HOME=/home/eval`), and on the host the files belong to the user who runs the harness. Claude Code thus does not run as root.

### Result files

The default run directory is `~/daybook-evidence/local-llm/eval/<run-id>/`, where `<run-id>` is `<UTC time>-<configuration name>`.

```
<run-id>/
  run.json                 configuration values, server values, image, Claude Code version, tasks
  run.log                  one progress line for each trial
  server.log               the full log of a managed server
  <task-id>-r<rep>/
    result.json            the result of the trial
    transcript.jsonl       the stream-json output of Claude Code
    agent.stderr           stderr of the agent container
    agent.diff             the agent work against the start commit
    verify.json            the output of the check
    check/                 verify.json, check.stdout, check.stderr, logs of verify.sh
    work/                  the workspace after the check
    claude-config/         the configuration directory after the trial (session files)
    memory.csv             the memory sampler (see "Observers")
    server.log             the server log of the trial (see "Observers")
    harness_error.txt      only for a harness error: the traceback
```

`result.json` has: `passed`, `score`, `failure_reason`, `failure_detail`, `wall_time_s` (agent container), `turns`, `tool_calls`, `tool_errors`, `api_errors`, `tokens`, `agent` (exit code, result subtype, durations), `verify`, `server` and `memory` (see "Observers"), `claude_code_version`, `image` (ID and digest), `config` (name, path, SHA-256) and `baseline` (start commit).

A trial passes only if Claude Code stops normally and the check passes. The failure reasons, in the order the harness examines them:

| Reason | Meaning |
|---|---|
| `timeout` | The agent container ran longer than `timeout_s` |
| `harness_error` | The check did not give a valid `verify.json`, Claude Code gave no result event, or the harness had an error. Not a model failure |
| `max_turns` | Claude Code stopped at `--max-turns` |
| `context_overflow` | An API error that says that the prompt is too long for the context |
| `api_error` | Another API error |
| `verify_failed` | The check failed |

## Task contract

```
tasks/<task-id>/
  task.toml     id, title, category, language, quick, timeout_s, max_turns
  prompt.md     the text that the agent gets
  workspace/    the start files. The harness copies them to /work
  verify/       hidden from the agent
    verify.sh   the check
  solution/     the reference solution: the harness copies its files over the workspace
```

```toml
id = "go-bugfix"          # same as the directory name
title = "Correct the duration parser"
category = "bugfix"       # bugfix, feature, investigate, long-context, constraints, tests, config
language = "go"
quick = true              # true: the task is also in the quick tier
timeout_s = 1800          # wall time limit of the agent
max_turns = 60
```

Rules for `verify.sh`:

- It runs as `bash /verify/verify.sh` in the check container. The working directory is `/work` (writable). `/verify` is read-only. `/out` is writable. There is no network. `EVAL_BASELINE` is the SHA of the start commit. The limit is 300 s.
- It writes `/out/verify.json`: `{"passed": bool, "score": 0.0 to 1.0, "checks": [{"name": str, "passed": bool}]}`. `passed` is true only if all checks pass. `score` is the fraction of the checks that pass.
- Its exit code is 0 when it wrote the file, also when a check failed. A missing or invalid file, or an exit code that is not 0, is a harness error.
- It works for each user ID and does not need `HOME`. It sets its tool variables (`GOCACHE`, `GOPROXY=off`, `GOFLAGS`, `CARGO_TARGET_DIR`, `CARGO_HOME`) to paths below `/tmp`. It writes only to `/work`, `/out` and `/tmp`.
- It does not trust files that the agent can change. It copies its hidden tests into the workspace and replaces test files with the same name.

Other rules:

- A task works with no network: standard library only, or vendored dependencies.
- `prompt.md` does not tell the agent how the check works.
- If `solution/apply.sh` exists, the harness does not copy it. It runs it with `bash` in a container after the copy, in `/work`, for example to make a commit.

## Add a task

1. Make `tasks/<task-id>/` with the files above. Use `tasks/go-bugfix/` as an example.
2. Make the task difficult enough: the agent must read more than one file, and the prompt must not name the cause.
3. Write `verify/verify.sh`. Make one named check for each behavior, so that `score` shows partial work.
4. Run `just selfcheck <task-id>`. The check must fail on the start files and pass with the solution. `run` does not start trials when a task fails the selfcheck. `uv run llm-eval selfcheck --keep <task-id>` keeps the scratch directory with the logs of `verify.sh`.

## Image

The image is built with `just image`. The base images (`golang:1.27`, `rust`) are pinned by digest. The yq binary is pinned by version and SHA-256. Claude Code is the binary of the host, checked by SHA-256. The Debian packages (jq, ripgrep, shellcheck, socat) come from Debian 13 and can get security updates in a rebuild.
