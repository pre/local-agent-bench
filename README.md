# llm-eval

Evaluation harness for a local LLM application: Claude Code (headless, `claude -p`) connected to a local inference server. The harness gives one comparable result for each configuration (model, server flags, client settings).

On the host only podman and the orchestrator (`uv run llm-eval`) run. The agent and the hidden check run in containers.

## Use

```sh
just image                                      # build localhost/llm-eval-agent:latest
just selfcheck                                  # check all tasks without an LLM
just run configs/qwen38-external.toml --task go-bugfix
just run configs/qwen38-external.toml --reps 3 --out ~/daybook-evidence/local-llm/eval/my-run
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

`result.json` has the SHA-256 of the configuration values. Not available yet: `mode = "managed"` and the `base` key.

## Network

`agent_network = "proxy"` (the default) is the most isolated mode. The agent container has no network (`--network=none`). The harness listens on a Unix socket and sends each connection to the server URL. In the container, socat listens on `127.0.0.1:8080` and sends each connection to that socket. Thus Claude Code reaches only the server: no internet, no DNS, no other host service.

Another value of `agent_network` goes to `podman run --network`, and `agent_url` is then the server URL in the container. These modes are less isolated. Examples:

- `container:llama-qwen38` with `agent_url = "http://127.0.0.1:8080"`: the agent uses the network namespace of the server container. The agent can also reach the internet through it.
- `slirp4netns:allow_host_loopback=true` with `agent_url = "http://10.0.2.2:8080"`: the agent can reach the internet and all services on the loopback interface of the host.

The check container always has no network.

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
  run.json                 configuration values, image, Claude Code version, tasks
  <task-id>-r<rep>/
    result.json            the result of the trial
    transcript.jsonl       the stream-json output of Claude Code
    agent.stderr           stderr of the agent container
    agent.diff             the agent work against the start commit
    verify.json            the output of the check
    check/                 verify.json, check.stdout, check.stderr, logs of verify.sh
    work/                  the workspace after the check
    claude-config/         the configuration directory after the trial (session files)
```

`result.json` has: `passed`, `score`, `failure_reason`, `failure_detail`, `wall_time_s` (agent container), `turns`, `tool_calls`, `tool_errors`, `api_errors`, `tokens`, `agent` (exit code, result subtype, durations), `verify`, `server` and `memory` (empty, for stage 2), `claude_code_version`, `image` (ID and digest), `config` (name, path, SHA-256) and `baseline` (start commit).

A trial passes only if Claude Code stops normally and the check passes. The failure reasons, in the order the harness examines them:

| Reason | Meaning |
|---|---|
| `timeout` | The agent container ran longer than `timeout_s` |
| `harness_error` | The check did not give a valid `verify.json`, or Claude Code gave no result event. Not a model failure |
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
