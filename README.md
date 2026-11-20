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
