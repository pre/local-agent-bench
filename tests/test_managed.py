import hashlib
import json
import socket
from pathlib import Path

import pytest

from fakes import FakePodman
from llm_eval.config import load_config
from llm_eval.server import ManagedServer, ServerError, llama_server_args, open_server
from test_server import http_server  # noqa: F401  (fixture)

NAME = "llm-eval-server"

CONFIG = """
name = "small"

[server]
mode = "managed"
image = "example.org/llama@sha256:abc"
models_dir = "{models}"
model_file = "q4/m-00001-of-00002.gguf"
model = "m"
context_tokens = 4096
api_key_file = "{key}"
port = {port}
chat_template = "templates/t.jinja"
gtt_max_used_mib = 1000
start_timeout_s = {timeout}

[server.args]
-ngl = 999
--jinja = true
--temp = 0.6
--no-mmap = false

[server.draft]
model_file = "mtp/d.gguf"
args = {{ --spec-type = "draft-mtp", --spec-draft-n-max = 3 }}
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "repo"
    (root / "templates").mkdir(parents=True)
    (root / "templates" / "t.jinja").write_text("{{ messages }}\n")
    models = tmp_path / "models"
    (models / "q4").mkdir(parents=True)
    (models / "mtp").mkdir()
    (models / "q4" / "m-00001-of-00002.gguf").write_bytes(b"x" * 10)
    (models / "q4" / "m-00002-of-00002.gguf").write_bytes(b"x" * 20)
    (models / "mtp" / "d.gguf").write_bytes(b"x" * 5)
    (tmp_path / "key").write_text("k1\n")
    return root


def write_config(repo: Path, url: str | None = None, timeout: int = 5, **replace: str) -> Path:
    port = int(url.rsplit(":", 1)[1]) if url else free_port()
    text = CONFIG.format(models=repo.parent / "models", key=repo.parent / "key", port=port, timeout=timeout)
    for old, new in replace.items():
        text = text.replace(old, new)
    path = repo / "c.toml"
    path.write_text(text)
    return path


def managed(repo, podman, gtt_mib=500, replace=False, **kw) -> ManagedServer:
    cfg = load_config(write_config(repo, **kw))
    return open_server(cfg.server, repo / "scratch", podman=podman, root=repo, out_dir=repo / "run",
                       replace=replace, gtt_used=lambda: gtt_mib, sleep=lambda s: None)


def test_llama_server_args(repo):
    cfg = load_config(write_config(repo))

    assert llama_server_args(cfg.server) == [
        "--host", "0.0.0.0", "--port", "8080", "--api-key-file", "/run/api-key",
        "-m", "/models/q4/m-00001-of-00002.gguf", "--alias", "m", "-c", "4096",
        "-ngl", "999", "--jinja", "--temp", "0.6",
        "--chat-template-file", "/run/chat-template.jinja",
        "-md", "/models/mtp/d.gguf", "--spec-type", "draft-mtp", "--spec-draft-n-max", "3",
    ]


def test_life_cycle(repo, http_server):
    podman = FakePodman()
    podman.server_log = "server log k1\n"

    with managed(repo, podman, url=http_server) as server:
        assert podman.containers[NAME]["labels"] == {"llm-eval.role": "server"}
        assert server.agent_access().network == "none"
        info = server.describe()

    assert NAME not in podman.containers
    (run,) = [c for c in podman.calls if c[:2] == ["run", "-d"]]
    gpu = "--runtime crun --device /dev/kfd --device /dev/dri/renderD128 --group-add keep-groups"
    assert f"{gpu} --security-opt seccomp=unconfined" in " ".join(run)
    port = http_server.rsplit(":", 1)[1]
    assert run[run.index("-p") + 1] == f"127.0.0.1:{port}:8080"
    volumes = [run[i + 1] for i, a in enumerate(run) if a == "-v"]
    assert volumes == [f"{repo.parent / 'models'}:/models:ro", f"{repo.parent / 'key'}:/run/api-key:ro",
                       f"{repo / 'templates' / 't.jinja'}:/run/chat-template.jinja:ro"]
    assert run[run.index("example.org/llama@sha256:abc") + 1] == "llama-server"
    assert ["stop", "-t", "60", NAME] in podman.calls
    assert (repo / "run" / "server.log").read_text() == "server log <redacted>\n"

    assert info["mode"] == "managed"
    assert info["container"] == NAME
    assert info["image"] == "example.org/llama@sha256:abc"
    assert info["image_digest"] == "sha256:serverdigest"
    assert info["llama_server_version"] == "version: 1.0.0-dev (build 12531, commit e4b620af1)"
    assert info["llama_server_args"] == llama_server_args(load_config(repo / "c.toml").server)
    assert info["podman_args"] == run
    assert info["model_files"] == [{"name": "q4/m-00001-of-00002.gguf", "bytes": 10},
                                   {"name": "q4/m-00002-of-00002.gguf", "bytes": 20}]
    assert info["draft_model_files"] == [{"name": "mtp/d.gguf", "bytes": 5}]
    template_sha = hashlib.sha256(b"{{ messages }}\n").hexdigest()
    assert info["chat_template"] == {"path": "templates/t.jinja", "sha256": template_sha}
    assert info["load_seconds"] >= 0
    assert info["gtt_used_before_start_mib"] == 500
    json.dumps(info)


def test_server_is_removed_when_the_body_raises(repo, http_server):
    podman = FakePodman()

    with pytest.raises(KeyboardInterrupt):
        with managed(repo, podman, url=http_server):
            raise KeyboardInterrupt

    assert NAME not in podman.containers


def test_gtt_guard_names_the_running_containers(repo):
    podman = FakePodman()
    podman.containers["llama-qwen38"] = {"labels": {}, "running": True}

    with pytest.raises(ServerError, match=r"(?s)GTT used is 2000 MiB.*1000.*llama-qwen38"):
        managed(repo, podman, gtt_mib=2000).__enter__()

    assert "llama-qwen38" in podman.containers
    assert not any(c[0] in ("run", "stop", "rm") for c in podman.calls)


def test_server_that_stops_during_the_start(repo):
    podman = FakePodman()
    podman.server_runs = False
    podman.server_log = "error: failed to load model\n"

    with pytest.raises(ServerError, match="(?s)stopped during the start.*failed to load model"):
        managed(repo, podman).__enter__()

    assert NAME not in podman.containers
    assert (repo / "run" / "server.log").exists()


def test_server_that_is_not_healthy_in_time(repo):
    podman = FakePodman()

    with pytest.raises(ServerError, match="not healthy after 0 s"):
        managed(repo, podman, timeout=0).__enter__()

    assert NAME not in podman.containers


def test_podman_run_failure(repo):
    podman = FakePodman()
    podman.run_exit_code = 125

    with pytest.raises(ServerError, match="podman run"):
        managed(repo, podman).__enter__()


def test_container_from_an_earlier_run_needs_replace(repo, http_server):
    podman = FakePodman()
    podman.containers[NAME] = {"labels": {"llm-eval.role": "server"}, "running": False}

    with pytest.raises(ServerError, match="--replace"):
        managed(repo, podman, url=http_server).__enter__()
    assert NAME in podman.containers

    with managed(repo, podman, url=http_server, replace=True):
        assert podman.containers[NAME]["running"] is True
    assert ["rm", NAME] in podman.calls


def test_foreign_container_is_never_removed(repo, http_server):
    podman = FakePodman()
    podman.containers[NAME] = {"labels": {}, "running": True}

    with pytest.raises(ServerError, match="did not start it"):
        managed(repo, podman, url=http_server, replace=True).__enter__()

    assert podman.containers[NAME]["running"] is True
    assert not any(c[0] in ("stop", "rm") for c in podman.calls)


@pytest.mark.parametrize("file", ["q4/m-00002-of-00002.gguf", "mtp/d.gguf"])
def test_missing_model_file(repo, file):
    podman = FakePodman()
    (repo.parent / "models" / file).unlink()

    with pytest.raises(ServerError, match=file):
        managed(repo, podman).__enter__()

    assert not any(c[0] == "run" for c in podman.calls)


def test_missing_chat_template(repo):
    (repo / "templates" / "t.jinja").unlink()

    with pytest.raises(ServerError, match="t.jinja"):
        managed(repo, FakePodman()).__enter__()


def test_failed_remove_is_reported(repo, http_server, capsys):
    podman = FakePodman()
    real_call = podman.call

    def call(args):
        if args[0] == "rm":
            podman.calls.append(args)
            return 2, "Error: helper stopped with SIGSYS\n"
        return real_call(args)

    podman.call = call

    with managed(repo, podman, url=http_server):
        pass

    err = capsys.readouterr().err
    assert "could not remove llm-eval-server" in err and "SIGSYS" in err
