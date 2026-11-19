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

# Write a Markdown report of run directories: just report <run-dir>... [--out file.md]
report *args:
    uv run llm-eval report {{args}}

# Compare two runs task by task
compare run_a run_b:
    uv run llm-eval compare {{run_a}} {{run_b}}

# Send the speed and protocol probes to the server of a configuration
probe config *args:
    uv run llm-eval probe --config {{config}} {{args}}

models_root := home_directory() / "models"
alpine := "docker.io/library/alpine@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc"

# Download models of download/models.tsv to ~/models/<name>/ in a detached container: just download-model gpt-oss-120b
[script("bash")]
download-model +names:
    set -euo pipefail
    mounts=()
    for name in {{names}}; do
      cut -f1 download/models.tsv | grep -qxF "$name" || { echo "unknown model: $name"; exit 1; }
      mkdir -p "{{models_root}}/$name"
      mounts+=(-v "{{models_root}}/$name:/models/$name")
    done
    podman run -d --replace --name model-download -e RATE="${RATE:-28M}" \
      -e SSL_CERT_FILE=/run/host-ca.crt \
      -v {{ca_file}}:/run/host-ca.crt:ro -v {{ca_file}}:/etc/ssl/certs/ca-certificates.crt:ro \
      -v "{{justfile_directory()}}/download/models.tsv:/run/models.tsv:ro" \
      -v "{{justfile_directory()}}/download/download.sh:/run/download.sh:ro" \
      "${mounts[@]}" {{alpine}} sh /run/download.sh {{names}}
    echo "Progress: podman logs -f model-download"

# Check the files of downloaded models with SHA-256, at low CPU and I/O priority
[script("bash")]
verify-model +names:
    set -euo pipefail
    for name in {{names}}; do
      (cd "{{models_root}}/$name" && cut -f1 expected-sha256.tsv | nice -n 19 ionice -c 3 sha256sum -c -)
    done
