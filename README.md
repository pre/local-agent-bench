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
just download-model gpt-oss-120b                # download model files (see "Models")
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
| `download/` | The list of model files (`models.tsv`) and the download script (see "Models") |
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
gtt_min_margin_mib = 4096                    # optional, see "Server control"
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

A model file that has its MTP layer inside (for example Qwen3.8-27B of unsloth) needs no draft file. Then put the flags in `[server.args]`: `--spec-type = "draft-mtp"`, `--spec-draft-n-max = 2`. `[server.draft]` is only for a separate draft file: without `model_file` the harness ignores its `args`.

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
| `qwen38-effort-medium.toml` | `CLAUDE_CODE_EFFORT_LEVEL=medium` (and the server value `--chat-template-kwargs '{"reasoning_effort":"medium"}'`) |
| `qwen38-effort-low.toml` | `CLAUDE_CODE_EFFORT_LEVEL=low` (and the server value `--chat-template-kwargs '{"reasoning_effort":"low"}'`) |
| `qwen38-iq4-xs.toml` | Quant UD-IQ4_XS |
| `qwen38-kv-f16.toml` | `-ctk f16 -ctv f16` |
| `qwen38-ctx-65536.toml` | `-c 65536`, and Claude Code gets the same value |
| `qwen38-no-mtp.toml` | No draft model |
| `qwen38-temp-0.6.toml` | `--temp 0.6` |
| `qwen38-external.toml` | External: the server `llama-qwen38` that runs already |

The chat template accepts the reasoning effort values xhigh (the default), medium and low. It uses xhigh for "high" and "max", and low for "minimal". Another value gives HTTP 400 for each request. With xhigh and low the template adds one instruction line to the system prompt, with medium it adds no line.

### What Claude Code sends

Recorded with Claude Code 2.1.328 in the agent container, with the environment of a trial, against a recording server (2026-11-19). The first request of a trial:

| Field | Value |
|---|---|
| `model` | the `model` of the configuration |
| `max_tokens` | 32000 |
| `temperature`, `top_p`, `top_k` | not sent |
| `thinking` | `{"type": "adaptive"}`. Not sent with `MAX_THINKING_TOKENS=0` or `CLAUDE_CODE_DISABLE_THINKING=1` |
| `output_config` | `{"effort": "high"}`. `CLAUDE_CODE_EFFORT_LEVEL` changes it to `low`, `medium`, `high`, `xhigh` or `max`. Another value (for example `minimal`) gives `high` |
| `stream` | true |
| Tools | 21 |
| `system` | 2 blocks, 7376 characters |
| `messages` | a user message, then a system message (8606 characters: environment, agent types, skills) |
| `anthropic-beta` | `claude-code-20250219,interleaved-thinking-2025-05-14,effort-2025-11-24` |

Consequences:

- llama-server (since PR 32321) gives `output_config.effort` to the chat template as `reasoning_effort`. The request value replaces `--reasoning-effort` and the `reasoning_effort` of `--chat-template-kwargs`. Thus `CLAUDE_CODE_EFFORT_LEVEL` in `[client.env]` controls the effort. The server value applies only to a request without an effort, for example the protocol probe.
- The server flags `--temp`, `--top-p`, `--top-k` and `--min-p` control the sampling, because Claude Code sends no sampling values.
- The system message after the first user message must be supported by the chat template. The original Qwen3.8 template rejects it, and the gpt-oss template drops it with no error.

## Models

| File | Model, quant | Files | Expected GTT | License | Known caveat |
|---|---|---|---|---|---|
| `qwen38-base.toml` | Qwen3.8-Flash-Next, UD-Q4_K_XL, MTP head | 4 parts and a draft file | 88017 MiB GTT used with the desktop (measured) | Qwen Community License | Needs the patched chat template and `-lzm on` |
| `gpt-oss-120b.toml` | gpt-oss-120b, F16 of unsloth (MXFP4 experts) | 1 file, 65.4 GB | about 68 GiB (estimate) | Apache 2.0 | The embedded template drops each system message after the first message, thus also the environment block of Claude Code |
| `qwen3-coder-next.toml` | Qwen3-Coder-Next 80B-A3B, UD-Q8_K_XL | 3 parts, 86.3 GB | about 85 to 87 GiB (estimate) | Apache 2.0, card metadata only (the LICENSE link gives HTTP 404) | No thinking mode |
| `qwen38-27b.toml` | Qwen3.8-27B dense, Q8_0, MTP layer inside | 1 file, 29.0 GB | about 37 GiB (estimate) | Apache 2.0 | Needs the patched chat template of Flash-Next. MTP with no draft file |
| `glm-53-flash.toml` | GLM-5.3 Flash 320.8B-A18B, UD-IQ2_XXS, no MTP | 4 parts, 101.8 GB | about 93 to 95 GiB (estimate) | MIT | At the memory limit: starts only when GTT used is 6000 MiB or less. Published top-1 agreement 76 %. Reports of reasoning that collapses in long sessions |

The four new configurations use `-lm none` (resident load, recommended on Strix Halo), port 8090, context 131072 and the image of `qwen38-base.toml`. The comments of each file give the source of each value. A unit test checks that each flag of each configuration is in the help text of llama-server build 12531 (`tests/llama-server-help-build12531.txt`).

### Download

```sh
just download-model gpt-oss-120b qwen3-coder-next   # detached container "model-download"
podman logs -f model-download                       # progress, "VERIFIED <model>" or "FAILED <model>"
just verify-model gpt-oss-120b                      # SHA-256 check on the host
```

`download/models.tsv` has one line for each file: model (the directory below `~/models`), repository, revision, date of the revision, path, size and SHA-256 (from the tree API of Hugging Face). The URL has the pinned revision, not `main`.

`download/download.sh` runs in an Alpine container (pinned by digest) with the CA bundle of the host. It does the models one after the other. For each model it writes `expected-sha256.tsv` and `source.txt` in the model directory, downloads the missing files with aria2 (16 connections for each file, `.part` files, a second run continues them), and checks each file with SHA-256 at low CPU and I/O priority. A file that does not match is downloaded again once. `RATE` (default `28M`, aria2 unit MiB/s) is the limit for all connections together.

## Cloud reference models

Two configurations run the same tasks with Claude models through the company LLM gateway. They show the distance between a local model and a cloud model. Each trial costs gateway tokens.

| File | Model ID of the gateway |
|---|---|
| `claude-sonnet-5.5-gateway.toml` | `Claude-Sonnet-5-5` |
| `claude-opus-5.5-gateway.toml` | `Claude-Opus-5-5` (base: the Sonnet file) |

```sh
just run configs/claude-sonnet-5.5-gateway.toml --task go-bugfix
```

The model IDs come from the model list of the gateway (`GET <url>/v1/models`, the list that `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY` uses). The configurations do not use the `[1m]` variant and do not set `context_tokens`. Claude Code 2.1.328 gives these two models a context window of 1000000 tokens also without `[1m]` (`model_usage.contextWindow` in `result.json`). To compare at the context window of a local model, set `context_tokens`.

```toml
[server]
mode = "remote"                         # an HTTPS endpoint. No container, no API key file
url = "https://llm-api.amd.com/Unified" # ANTHROPIC_BASE_URL, must start with https://
model = "Claude-Sonnet-5-5"             # the model ID for all Claude Code model variables
# context_tokens = 200000               # optional: CLAUDE_CODE_MAX_CONTEXT_TOKENS. Default: not set
# ca_file = "/etc/ssl/certs/ca-certificates.crt"  # the default. Read-only in the agent container
# agent_network = "proxy"               # the default, see below

[client.env]                            # values that are not secret
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"

[client.secrets]                        # secret values, read at run time
from_profile = "~/.config/claude-code/profiles/llm-gw.sh"
names = ["ANTHROPIC_API_KEY", "ANTHROPIC_CUSTOM_HEADERS"]
```

The remote mode does not have these steps of a local server: start of a container, GTT check, `/health` check, server observer. Before the run and before each trial, the harness sends a request without credentials to `url`. Each HTTP status (also 401) shows that the endpoint answers.

Model tiers: `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_{FABLE,OPUS,SONNET,HAIKU}_MODEL` and `CLAUDE_CODE_SUBAGENT_MODEL` all get `model`, so the result belongs to one model. The reasoning effort stays at the default of Claude Code.

### Secrets

`[client.secrets]` can be in each configuration. Before the first trial a `bash` process sources `from_profile` with a small environment (`HOME`, `PATH`) and writes only the values of `names` to a pipe. If the profile does not set a name, the run stops. The values:

- go to podman through its process environment (`-e NAME` without a value), not through its arguments.
- are not in `run.json`: the configuration has only the profile path and the names.
- are replaced with `<redacted>` in all files of the trial directory after the trial. For `ANTHROPIC_CUSTOM_HEADERS` the harness also replaces the value of each `Name: value` line (the subscription key). The harness replaces each occurrence, also in the work files. A value shorter than 8 characters is a placeholder and is not replaced, because its replacement changes normal text in files that contain no secret.

A local server gives `ANTHROPIC_AUTH_TOKEN` (its API key). A remote endpoint gives no key of its own, so the local key does not go to the gateway.

The agent can read its environment, for example with `env` in a Bash command. Thus the secret values can be in the transcript before the redaction.

### Network of a remote endpoint

With `agent_network = "proxy"` the agent container has no network (`--network=none`), the same as for a local server:

1. The harness listens on a Unix socket (`<scratch>/relay/api.sock`). It accepts only `CONNECT <host>:<port>` to the host and port of `url`. It refuses each other request with HTTP 403, and gives HTTP 502 when the endpoint is not reachable.
2. In the container, socat listens on `127.0.0.1:8080` and sends each connection to that socket.
3. Claude Code gets `HTTPS_PROXY=http://127.0.0.1:8080`, `ANTHROPIC_BASE_URL=<url>`, and `NODE_EXTRA_CA_CERTS` and `SSL_CERT_FILE` with the CA bundle of the host at `/run/llm-eval-ca.crt` (read-only). `NO_PROXY` is not set, so each HTTPS connection goes to the proxy.

TLS goes from Claude Code to the gateway through the tunnel. The harness does not see the request. The TLS proxy of the company network (ZScaler) intercepts it on the way, thus the container needs the CA bundle of the host. The container has no DNS. The proxy gets the host name and resolves it on the host.

The agent can reach only the gateway host on its port: no other host, no DNS, no service of the host. Telemetry of Claude Code and other requests of the agent get HTTP 403. The agent can use the secret values with the gateway, for example with curl.

Another value of `agent_network` goes to `podman run --network` (for example `slirp4netns`), and Claude Code connects to `url` directly. This mode is less isolated: the agent can reach the internet.

### Model and cost in the result

`result.json` of each trial also has:

- `total_cost_usd`: the value of the Claude Code `result` event. Claude Code calculates it from its own price list, so it is an estimate. For a local server it has no meaning.
- `model_usage`: the `modelUsage` value of the `result` event (tokens and cost for each model that Claude Code requested).
- `models`: the model IDs of the API responses (`message.model` of the assistant events).

`run.json` has `reported_models`: the `models` of all trials. If the gateway gives a different model than the configuration requests, this list shows it.

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
5. Wait until `/health` gives HTTP 200 (limit `start_timeout_s`). If the container stops, the harness shows the end of its log. At each poll the harness reads GTT used. If GTT total (`mem_info_gtt_total`) minus GTT used is less than `gtt_min_margin_mib` (default 4096), the harness stops and removes the container and stops the run of this configuration with a message that gives the two values. Thus a model that is too large fails its start and does not stop the desktop.
6. Run the trials. Before each trial the harness checks `/health`. If the server is down, the run of this configuration stops (continue it later with `--resume`).
7. Stop the container (`podman stop -t 60`), save its full log as `server.log` in the run directory, remove the container. The harness also does this step when a trial raises an error or when you push Ctrl-C.

`run.json` gets `server` with the values that make the result reproducible: `llama_server_args` (the full argument list), `podman_args`, `image` and `image_digest`, `llama_server_version` (the build line of `llama-server --version`, because the log does not show it at the default verbosity), `model_files` and `draft_model_files` (name and size of each part), `chat_template` (path and SHA-256) and `load_seconds` (from the start of the container to the first healthy `/health`). It also gets the GTT values of the start, in MiB:

- `gtt_used_before_start_mib`: GTT used before the start, that is, the GTT of the other programs.
- `gtt_used_after_load_mib`: GTT used after the first healthy `/health`.
- `gtt_used_load_peak_mib`: the highest GTT used during the wait for `/health`.
- `gtt_total_mib`: GTT total, the limit of the kernel.

For an external server, `server` has the mode, the URL, the container and `gtt_total_mib`. The harness does not see the start of an external server, thus it has no other GTT values. A remote endpoint has no GTT values.

## Observers

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
6. Write `result.json`. Then replace the API key and the secret values of `[client.secrets]` with `<redacted>` in all files of the trial.

Containers:

| Container | Mounts | Network | Environment |
|---|---|---|---|
| Agent | `<trial>/work:/work`, `<trial>/claude-config:/claude-config`, relay directory at `/run/llm-eval` (proxy mode), CA bundle at `/run/llm-eval-ca.crt:ro` (remote mode) | `none` (proxy mode) | `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` (local server: from the key file), the values of `[client.secrets]` (secret values are not in the podman arguments), `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_{FABLE,OPUS,SONNET,HAIKU}_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_MAX_CONTEXT_TOKENS` (when `context_tokens` is set), `HTTPS_PROXY`, `NODE_EXTRA_CA_CERTS` and `SSL_CERT_FILE` (remote mode), `[client.env]` |
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
  probes/                  only with run --probe (see "Probes in a run")
    protocol.json          the protocol probe
    speed.json             the speed probe
    memory.csv             the memory sampler during the probes
    memory.json            the memory summary of the probes, the keys of "memory" in result.json
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

`result.json` has: `passed`, `score`, `failure_reason`, `failure_detail`, `wall_time_s` (agent container), `turns`, `tool_calls`, `tool_errors`, `api_errors`, `tokens`, `total_cost_usd`, `model_usage` and `models` (see "Cloud reference models"), `agent` (exit code, result subtype, durations), `verify`, `server` and `memory` (see "Observers"), `claude_code_version`, `image` (ID and digest), `config` (name, path, SHA-256) and `baseline` (start commit).

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

## Report

```sh
just report ~/daybook-evidence/local-llm/eval/<run-id> [<run-id>...]
uv run llm-eval report <run-dir>... --out report.md
```

`report` reads `run.json` and each `*/result.json` of the run directories and writes Markdown to stdout or to the `--out` file. The report has these parts:

| Part | Content |
|---|---|
| Runs | Each run directory: trials found and expected, start and end time. A run that is not finished, or that has fewer results than tasks times repetitions, is marked PARTIAL |
| Configurations | One row for each configuration: trials counted, pass rate with a 95 % Wilson interval, mean score, median and total wall time, prompt and decode tokens per second, draft acceptance, GTT peak, lowest MemAvailable, lowest SwapFree, count of each failure reason, count of harness errors |
| Memory | One row for each configuration: GTT limit, GTT before start, GTT after load, GTT peak, Model GTT, GTT margin, lowest MemAvailable, lowest SwapFree, highest PSI full avg10 |
| Tasks | Task against configuration: passes of the counted repetitions (for example `2/3`). The mean score is shown when a trial has a partial score |
| Failed trials | For each configuration: run, task, repetition, failure reason, score, failed check names, turns, wall time |
| Limits | The count of trials and the width of the interval for each configuration |
| Probes | The speed and protocol probe results, when the run directory has `probes/speed.json` or `probes/protocol.json` |

Rules:

- A configuration is a name and the SHA-256 of its values. The same name with a different SHA-256 is a different row, and the row label has the first 8 characters of the SHA-256.
- A trial with `harness_error` is not a model failure. It is not in the pass rate, the mean score and the median wall time. The total wall time includes it.
- Rows are sorted by pass rate, then by median wall time.
- Speed values come from the `server` dictionary of `result.json`: the sum of the tokens divided by the sum of the seconds of all trials, not a mean of rates. Draft acceptance is the sum of accepted tokens divided by the sum of generated draft tokens.
- Memory values come from the `memory` dictionary of the trials and from `probes/memory.json`: the peak of the peaks and the minimum of the minimums. GTT peak also includes `gtt_used_load_peak_mib` of `run.json`. A value is `n/a` when no trial has it.
- All memory values are measured on the machine of the run. The report reads only the run files, not `/sys`, thus it can run later or on a different machine.
- In "Memory", GTT limit is `gtt_total_mib`, GTT before start is `gtt_used_before_start_mib` and GTT after load is `gtt_used_after_load_mib` of `run.json`. Model GTT is GTT peak minus GTT before start: the GTT of the server with its model and context. GTT margin is GTT limit minus GTT peak.
- A run without `gtt_used_after_load_mib` (an older run) gives GTT after load from `gtt_used_start_mib` of its first trial. A run without `gtt_total_mib` gives `n/a` for GTT limit and GTT margin. An external server gives `n/a` for GTT before start and Model GTT.
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

## Probe

```sh
just probe configs/qwen38-external.toml                       # all probes, all speed targets
just probe configs/qwen38-external.toml --kind protocol
just probe configs/qwen38-external.toml --kind speed --target 1000 --target 23000
```

### Probes in a run

`run --probe speed|protocol|all` sends the probes to the server of each run after the server is healthy and before the first trial. The files go to `<run-dir>/probes/`, so `report <run-dir>` shows them. The speed probe of a run uses the targets 1000 and 23000 tokens. `--probe-target N` (can repeat) gives other targets.

The memory sampler runs during the probes and writes `probes/memory.csv` and `probes/memory.json`. A long prompt fills the context, thus a probe can use more GTT than the trials. The GTT peak of the report includes the probes.

With `protocol` or `all`, the protocol probe runs first, and it is a gate. When the case `plain`, `tool_call` or `tool_round_trip` fails, the harness does not run the speed probe and the trials of that configuration. It prints the failed cases, writes the reason to `run.json` (key `probe_gate`: `failed_cases`, `reason`, `at`) and to `run.log`, stops the server and continues with the next configuration. The exit code is then 1. The report shows the reason in "Runs". The other cases do not stop a run.

### Probe command

`probe` sends requests from the host directly to the server URL of the configuration, with the key of `api_key_file`. It does not use Claude Code or a container. The results go to `<out>/probes/speed.json` and `<out>/probes/protocol.json`. The default `<out>` is `~/daybook-evidence/local-llm/eval/probe-<UTC time>-<configuration>/`. `report <out>` shows the probe results.

The probes are polite to a shared server. They send one request at a time. Before each request they read `/slots` and wait (at most 300 s) until no slot processes a request. Each request has a timeout (`--timeout`, default 1800 s). The timeout is for each read of the socket, and the server sends no data while it processes the prompt.

Other code can call `llm_eval.probe.probe_server(base_url, api_key, model, out_dir, ...)`, for example for a managed server.

### Speed probe

For each target (default 1000, 23000, 60000 and 120000 tokens) the probe sends one streaming `/v1/chat/completions` request. The prompt has about the target count of tokens and asks for a long answer. The probe stops the answer at `--decode-tokens` (default 256) and switches off thinking with `chat_template_kwargs: {"enable_thinking": false}`.

- The prompt is real prose and code: the Python language reference (`pydoc_data.topics`) and 20 modules of the Python standard library, in alternate pieces of about 6000 characters. The probe uses `/tokenize` and `/detokenize` of llama-server to cut the text to the target size.
- A random nonce is at the start of the prompt. Thus the server cannot use its prompt cache, and it processes the full prompt again. `cache_tokens` shows the count of tokens that came from the cache.
- The speed values come from the `timings` object in the last chunk of the stream (llama.cpp). `/v1/messages` does not give timings. Time to first token is measured by the client: from the request to the first chunk with text.
- A target is skipped when it is above `context_tokens` of the configuration minus the decode tokens and a margin of 1024 tokens, or above `--max-context`. After a failed request the probe sends no more requests.
- On this machine (Qwen3.8 Flash-Next UD-Q4_K_XL with MTP, 2026-11-19) the 120000 token request took 785 s: 767 s for the prompt at 157 tokens per second. The full speed probe took about 20 minutes.

`speed.json`:

```json
{
  "schema": 1, "kind": "speed", "base_url": "...", "model": "...",
  "config": {"name": "...", "sha256": "..."},
  "server": {"build_info": "...", "model_path": "...", "total_slots": 1, "n_ctx": 131072},
  "started_at": "...", "finished_at": "...",
  "decode_tokens": 256, "corpus": "Python 3.15: pydoc topics and 20 standard library modules",
  "results": [{
    "target_tokens": 23000, "prompt_tokens": 23013, "cache_tokens": 0,
    "prompt_seconds": 73.7, "prompt_tps": 312.3,
    "decode_tokens": 256, "decode_seconds": 10.1, "decode_tps": 25.3,
    "ttft_s": 73.8, "total_s": 83.9,
    "draft_generated": 283, "draft_accepted": 160, "draft_acceptance": 0.565,
    "reasoning_chars": 0, "finish_reason": "length", "error": null, "waited_s": 0.0
  }],
  "skipped": [{"target_tokens": 120000, "reason": "above --max-context 30000"}]
}
```

A failed request gives `{"target_tokens": N, "error": "HTTP 503: ..."}`.

### Protocol probe

The protocol probe sends a fixed list of small requests to `/v1/messages`, the endpoint that Claude Code uses. Each case records the HTTP status, the error text and the result of one assertion on the response.

| Case | Request | Assertion |
|---|---|---|
| `plain` | One user message | The text has the requested word |
| `two_system_blocks` | Two system blocks at the start | The text has the codes of the two blocks |
| `system_in_middle` | A system message in the middle of the conversation | The text has the code of the system message. The original chat template of Qwen3.8 gave HTTP 500 "System message must be at the beginning" |
| `tool_call` | A question that needs a tool | A `tool_use` block, the input agrees with the schema |
| `tool_round_trip` | Assistant `tool_use`, user `tool_result` | The final text uses the tool result |
| `parallel_tools` | A question that needs two tools | Two `tool_use` blocks in one turn, each input agrees with its schema |
| `nested_arguments` | A tool with nested objects and arrays | The input agrees with the schema |
| `tool_result_error` | A `tool_result` with `is_error: true` | HTTP 200 with a text or a `tool_use` block |
| `stream_tool_call` | `stream: true` with a tool | The event sequence is well formed (`message_start` first, `message_stop` last, one open block at a time, block indexes in sequence, a `message_delta` with a stop reason) and the tool input JSON agrees with the schema |
| `thinking_budget` | `thinking: {"type": "enabled", "budget_tokens": 1024}` | The reasoning is in a `thinking` block, the text has the answer and no `<think>` tags |
| `thinking_disabled` | `thinking: {"type": "disabled"}` | No `thinking` block |
| `max_tokens` | `max_tokens: 16` and a long answer | `stop_reason` is `max_tokens` |
| `client_sampling` | `temperature`, `top_p` and `top_k` from the client | `/slots` shows the client values. Another client can change `/slots` between the two requests |
| `count_tokens` | `/v1/messages/count_tokens` | `input_tokens` is a positive integer |

To add a case, add one `Case` entry to `CASES` in `src/llm_eval/probe.py`: a name, a description, the request body and a check function.

`protocol.json` has the same header as `speed.json` (`schema`, `kind`, `base_url`, `model`, `config`, `server`, `started_at`, `finished_at`) and:

```json
{
  "cases": [{
    "name": "stream_tool_call", "description": "...", "path": "/v1/messages",
    "http_status": 200, "passed": false,
    "note": "1 tool calls: get_weather; block 1 starts before block 0 stops; ...",
    "error": null, "stop_reason": "tool_use", "seconds": 4.1,
    "response": "message_start, content_block_start(thinking), content_block_delta x20, ..."
  }],
  "passed": 12, "total": 14
}
```

`response` is the first 1500 characters of the response body, or a short list of the event types of a stream. `error` is the network error, or the HTTP status and the start of the body when the status is not 200.
