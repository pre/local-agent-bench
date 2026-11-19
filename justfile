# llm-eval: evaluation harness for Claude Code with a local inference server.
# On the host only podman and the orchestrator (uv run llm-eval) run.

set export

image := "localhost/llm-eval-agent:latest"
claude_version := env("CLAUDE_VERSION", "2.1.328")
claude_bin := home_directory() / ".local/share/claude/versions" / claude_version
ca_file := "/etc/ssl/certs/ca-certificates.crt"

SSL_CERT_FILE := ca_file
REQUESTS_CA_BUNDLE := ca_file
CURL_CA_BUNDLE := ca_file
NODE_EXTRA_CA_CERTS := ca_file
TMPDIR := env("TMPDIR", home_directory() / "tmp")

_default:
    @just --list

# Build the agent image (Claude Code of the host, Go, Rust, Python and the tools)
[script("bash")]
image:
    set -euo pipefail
    sum=$(sha256sum "{{claude_bin}}" | cut -c1-64)
    podman build -t {{image}} \
      --build-arg CLAUDE_VERSION={{claude_version}} --build-arg CLAUDE_SHA256="$sum" \
      -v "{{claude_bin}}:/run/claude-bin:ro" \
      -v {{ca_file}}:/etc/ssl/certs/ca-certificates.crt:ro \
      -f image/Containerfile image
    podman image inspect {{image}} --format 'image {{{{.Id}}'
    podman run --rm {{image}} claude --version

# Check each task without an LLM: the check fails on the start files and passes with the solution
selfcheck *tasks:
    uv run llm-eval selfcheck {{tasks}}

# Run trials: just run configs/qwen38-external.toml --task go-bugfix
run config *args:
    uv run llm-eval run --config {{config}} {{args}}

# Continue an interrupted run: just resume ~/daybook-evidence/local-llm/eval/<run-id>
resume run_dir *args:
    uv run llm-eval run --resume {{run_dir}} {{args}}

# Run the unit tests with coverage
test *args:
    uv run pytest --cov=llm_eval --cov-report=term-missing {{args}}
