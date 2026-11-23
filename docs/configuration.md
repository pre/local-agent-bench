# Configuration

```toml
name = "qwen38-external"             # default: the file name

[server]
mode = "external"                    # the server runs already, the harness does not start or stop it
url = "http://127.0.0.1:8080"        # URL on the host
api_key_file = "~/.config/llama-server/api-key"
model = "qwen3.8-flash-next"         # model ID for all Claude Code model variables
context_tokens = 131072              # CLAUDE_CODE_MAX_CONTEXT_TOKENS
health_path = "/health"              # optional, the harness checks it before the run
agent_network = "proxy"              # optional, see network.md
# agent_url = "http://10.0.2.2:8080" # necessary when agent_network is not "proxy"

[client]
image = "localhost/llm-eval-agent:latest"
config_dir = "client-config"

[client.env]                         # more environment variables for Claude Code
CLAUDE_CODE_ATTRIBUTION_HEADER = "0"
```

`result.json` has the SHA-256 of the configuration values. An external server can also have `container = "llama-qwen38"`: the name of its podman container. Then the harness reads the speed values from its log (see [Observers](observers.md)).

## Managed server

With `mode = "managed"` the harness starts a `llama-server` container for the run (see [Server control](server-control.md)):

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
gtt_max_used_mib = 12288                     # optional, see server-control.md
gtt_min_margin_mib = 4096                    # optional, see server-control.md
mem_available_min_mib = 2048                 # optional, 0 switches it off, see server-control.md
start_timeout_s = 900                        # optional, the time limit for /health
health_path = "/health"                      # optional
agent_network = "proxy"                      # optional, see network.md

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

A model file that has its MTP layer inside (for example, by report, Qwen3.8-27B of unsloth) needs no draft file. Then put the flags in `[server.args]`: `--spec-type = "draft-mtp"`, `--spec-draft-n-max = 2`. `[server.draft]` is only for a separate draft file: without `model_file` the harness ignores its `args`.

The harness sets these flags itself, and they are not permitted in `args`: `--host 0.0.0.0 --port 8080 --api-key-file /run/api-key -m /models/<model_file> --alias <model> -c <context_tokens>`, `--chat-template-file /run/chat-template.jinja` (with `chat_template`) and `-md /models/<draft model_file>` (with a draft model). `args` is a table and not a list, so a variant file can change one flag.

## Base and variants

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

## What Claude Code sends

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
- The system message after the first user message must be supported by the chat template. The original Qwen3.8 template rejects it, and the embedded gpt-oss template drops it with no error. `templates/gpt-oss-120b.jinja` keeps it (`gpt-oss-120b-sysmsg.toml`).
