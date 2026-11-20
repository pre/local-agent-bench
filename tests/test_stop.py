"""A stop signal during a run: llm-eval runs as a process with a fake podman on PATH.

The signals come the same way as in tmux: Ctrl-C sends SIGINT to the process
group (also to tee, so stdout and stderr become a closed pipe), and then tmux
closes the pane and sends SIGHUP to the process group.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fake_llama import KEY, FakeLlama
from test_task import make_task

TESTS = Path(__file__).parent
LLM_EVAL = Path(sys.executable).parent / "llm-eval"

CONFIG = """
name = "stop-test"

[server]
mode = "managed"
image = "example.org/llama@sha256:abc"
models_dir = "{models}"
model_file = "m.gguf"
model = "m"
context_tokens = 65536
api_key_file = "{key}"
port = {port}
gtt_max_used_mib = 100000000
gtt_min_margin_mib = 0
start_timeout_s = 60
"""


class Harness:
    def __init__(self, tmp_path: Path, llama: FakeLlama):
        self.llama = llama
        self.root = tmp_path / "repo"
        (self.root / "client-config").mkdir(parents=True)
        (self.root / "client-config" / "settings.json").write_text("{}")
        task = make_task(self.root / "tasks", "t1")
        (task / "workspace" / "main.txt").write_text("bug\n")
        (task / "solution" / "fixed.txt").write_text("")
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "m.gguf").write_bytes(b"x")
        (tmp_path / "key").write_text(KEY + "\n")
        port = llama.url.rsplit(":", 1)[1]
        self.config = self.root / "c.toml"
        self.config.write_text(CONFIG.format(models=tmp_path / "models", key=tmp_path / "key", port=port))
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        podman = bin_dir / "podman"
        podman.write_text(f'#!/bin/sh\nexec {sys.executable} {TESTS / "fake_podman.py"} "$@"\n')
        podman.chmod(0o755)
        self.state = tmp_path / "podman"
        self.state.mkdir()
        self.out = tmp_path / "out"
        self.env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_PODMAN_DIR": str(self.state),
                    "FAKE_PODMAN_STOP_S": "0.3", "PYTHONUNBUFFERED": "1"}
        self.processes: list[subprocess.Popen] = []

    def start(self, *args: str) -> subprocess.Popen:
        command = [str(LLM_EVAL), "--root", str(self.root), "run", "--config", str(self.config),
                   "--out", str(self.out), *args]
        proc = subprocess.Popen(command, env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, start_new_session=True)
        self.processes.append(proc)
        return proc

    def calls(self) -> list[dict]:
        path = self.state / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def ended(self, argv: list[str]) -> bool:
        return any(c["event"] == "end" and c["argv"] == argv and c["code"] == 0 for c in self.calls())

    def started(self, prefix: list[str]) -> bool:
        return any(c["event"] == "start" and c["argv"][:len(prefix)] == prefix for c in self.calls())

    def containers(self) -> list[str]:
        directory = self.state / "containers"
        return sorted(p.stem for p in directory.iterdir()) if directory.exists() else []


@pytest.fixture
def harness(tmp_path):
    llama = FakeLlama()
    llama.state.system_in_middle = "keep"
    h = Harness(tmp_path, llama)
    yield h
    for proc in h.processes:  # a failed test can leave the harness and its fake agent
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        if proc.stdout:
            proc.stdout.close()
    llama.stop()


def wait_for(condition, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not condition():
        assert time.monotonic() < deadline, "timeout"
        time.sleep(0.02)


class ServerStart:
    args: list[str] = []

    def prepare(self, h: Harness) -> None:
        h.llama.state.health_status = 503

    def wait(self, h: Harness) -> None:
        wait_for(lambda: h.started(["run", "-d"]) and ("GET", "/health", None) in h.llama.state.requests)


class SpeedProbe:
    args = ["--probe", "speed", "--probe-target", "1000"]

    def prepare(self, h: Harness) -> None:
        h.llama.state.hang.add("/v1/chat/completions")

    def wait(self, h: Harness) -> None:
        wait_for(lambda: any(path == "/v1/chat/completions" for _, path, _ in h.llama.state.requests))


class Trial:
    args: list[str] = []

    def prepare(self, h: Harness) -> None:
        pass

    def wait(self, h: Harness) -> None:
        wait_for(lambda: any(name.startswith("llm-eval-agent-") for name in h.containers()))


def reach(h: Harness, phase) -> subprocess.Popen:
    phase.prepare(h)
    proc = h.start(*phase.args)
    phase.wait(h)
    return proc


def ctrl_c_in_tmux(proc: subprocess.Popen) -> None:
    os.killpg(proc.pid, signal.SIGINT)
    proc.stdout.close()  # tee stops at SIGINT
    os.killpg(proc.pid, signal.SIGHUP)


def ctrl_c_with_tee(proc: subprocess.Popen) -> None:
    """The terminal stays open: no SIGHUP."""
    os.killpg(proc.pid, signal.SIGINT)
    proc.stdout.close()


def sigterm(proc: subprocess.Popen) -> None:
    proc.send_signal(signal.SIGTERM)


def sighup(proc: subprocess.Popen) -> None:
    os.killpg(proc.pid, signal.SIGHUP)


def assert_server_removed(h: Harness, proc: subprocess.Popen) -> None:
    assert proc.wait(timeout=30) == 130
    assert h.ended(["stop", "-t", "60", "llm-eval-server"])
    assert h.ended(["rm", "llm-eval-server"])
    assert h.containers() == []
    assert (h.out / "server.log").read_text() == "fake llama-server log\n"
    run_log = (h.out / "run.log").read_text()
    assert "llm-eval-server is removed" in run_log
    assert f"To continue: llm-eval run --resume {h.out}" in run_log


PHASES = {"server start": ServerStart(), "speed probe": SpeedProbe(), "trial": Trial()}


@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize("stop", [ctrl_c_in_tmux, sigterm, sighup])
def test_stop_signal_stops_and_removes_the_server(harness, phase, stop):
    proc = reach(harness, PHASES[phase])

    stop(proc)

    assert_server_removed(harness, proc)


def test_ctrl_c_with_a_closed_pipe_stops_and_removes_the_server(harness):
    proc = reach(harness, SpeedProbe())

    ctrl_c_with_tee(proc)

    assert_server_removed(harness, proc)


def test_stop_signal_during_a_trial_removes_the_agent_container(harness):
    proc = reach(harness, Trial())
    (agent,) = [name for name in harness.containers() if name.startswith("llm-eval-agent-")]

    ctrl_c_in_tmux(proc)

    assert_server_removed(harness, proc)
    assert harness.ended(["rm", "-f", "-t", "10", "--ignore", agent])
    assert (harness.out / "t1-r1" / "server.log").exists()


def test_more_signals_during_the_cleanup_do_not_stop_it(harness):
    harness.env["FAKE_PODMAN_STOP_S"] = "1"
    proc = reach(harness, SpeedProbe())
    ctrl_c_in_tmux(proc)
    wait_for(lambda: harness.started(["stop"]))

    for stop in (signal.SIGINT, signal.SIGHUP, signal.SIGTERM):
        os.killpg(proc.pid, stop)

    assert_server_removed(harness, proc)


def test_stop_messages_and_the_resume_hint_go_to_stderr(harness):
    proc = reach(harness, Trial())

    proc.send_signal(signal.SIGINT)

    output = proc.stdout.read().decode()
    assert proc.wait(timeout=30) == 130
    assert "llm-eval: stopping llm-eval-server" in output
    assert f"To continue: llm-eval run --resume {harness.out}" in output
