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
from llm_eval import cli
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
mem_available_min_mib = 0
start_timeout_s = 60
"""
GUARDED_LLM_EVAL = [sys.executable, str(TESTS / "guarded_llm_eval.py")]
MEMINFO = "MemTotal:       131072000 kB\nMemAvailable:   {kib} kB\nSwapFree:       8388604 kB\n"


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
                    "FAKE_PODMAN_STOP_S": "0.3"}  # no PYTHONUNBUFFERED: stdout is a block-buffered pipe
        self.processes: list[subprocess.Popen] = []
        self.llm_eval = [str(LLM_EVAL)]

    def start(self, *args: str) -> subprocess.Popen:
        command = [*self.llm_eval, "--root", str(self.root), "run", "--config", str(self.config),
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

    def call_time(self, prefix: list[str]) -> float | None:
        return next((c["time"] for c in self.calls() if c["event"] == "start" and c["argv"][:len(prefix)] == prefix),
                    None)

    def guard_on_a_fake_host(self, tmp_path: Path) -> None:
        """The memory guard reads fake host files: GTT total 112640 MiB, the limits are the defaults."""
        self.host = tmp_path / "host"
        (self.host / "card0" / "device").mkdir(parents=True)
        self._write("card0/device/mem_info_gtt_total", f"{112640 << 20}\n")
        self.set_host(gtt_used_mib=50000, mem_available_mib=30000)
        self.config.write_text(self.config.read_text().replace("gtt_min_margin_mib = 0\nmem_available_min_mib = 0\n",
                                                               ""))
        self.env["FAKE_HOST_DIR"] = str(self.host)
        self.llm_eval = GUARDED_LLM_EVAL

    def set_host(self, gtt_used_mib: int, mem_available_mib: int) -> float:
        """Write the values and return the time."""
        self._write("card0/device/mem_info_gtt_used", f"{gtt_used_mib << 20}\n")
        self._write("meminfo", MEMINFO.format(kib=mem_available_mib << 10))
        return time.time()

    def _write(self, name: str, text: str) -> None:
        """A rename: the guard does not read a part of the file."""
        temporary = self.host / f"{name}.tmp"
        temporary.write_text(text)
        temporary.rename(self.host / name)


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


def assert_server_removed(h: Harness, proc: subprocess.Popen, hint: str | None = None) -> None:
    assert proc.wait(timeout=30) == 130
    assert h.ended(["stop", "-t", "60", "llm-eval-server"])
    assert h.ended(["rm", "llm-eval-server"])
    assert h.containers() == []
    assert (h.out / "server.log").read_text() == "fake llama-server log\n"
    run_log = (h.out / "run.log").read_text()
    assert "llm-eval-server is removed" in run_log
    assert (hint or f"To continue: llm-eval run --resume {h.out}") in run_log


def restart_hint(h: Harness, *args: str) -> str:
    """Before the server is healthy, run.json does not exist and --resume does not work."""
    return f"To start it again: llm-eval run --config {h.config} --out {h.out}" + "".join(f" {a}" for a in args)


PHASES = {"server start": ServerStart(), "speed probe": SpeedProbe(), "trial": Trial()}


@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize("stop", [ctrl_c_in_tmux, sigterm, sighup])
def test_stop_signal_stops_and_removes_the_server(harness, phase, stop):
    proc = reach(harness, PHASES[phase])

    stop(proc)

    assert_server_removed(harness, proc, restart_hint(harness) if phase == "server start" else None)


@pytest.mark.parametrize("unbuffered", [False, True])
def test_ctrl_c_with_a_closed_pipe_stops_and_removes_the_server(harness, unbuffered):
    if unbuffered:
        harness.env["PYTHONUNBUFFERED"] = "1"
    proc = reach(harness, SpeedProbe())

    ctrl_c_with_tee(proc)

    assert_server_removed(harness, proc)


def test_restart_hint_of_a_stop_during_the_server_start_works(harness):
    phase = ServerStart()
    phase.args = ["--task", "t1", "--reps", "1", "--probe", "speed", "--probe-target", "1000"]
    proc = reach(harness, phase)
    sigterm(proc)
    hint = restart_hint(harness, *phase.args)
    assert_server_removed(harness, proc, hint)
    assert not (harness.out / "run.json").exists()
    harness.llama.state.health_status = 200
    harness.env["FAKE_PODMAN_AGENT_S"] = "0"

    command = hint.split("To start it again: llm-eval ", 1)[1].split()
    again = subprocess.run([str(LLM_EVAL), "--root", str(harness.root), *command],
                           env=harness.env, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)

    assert again.returncode == 0, again.stdout + again.stderr
    assert (harness.out / "run.json").exists() and (harness.out / "t1-r1" / "result.json").exists()


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


def test_signal_during_the_normal_stop_of_a_server_does_not_start_the_next(harness, tmp_path):
    second = harness.root / "d.toml"
    second.write_text(harness.config.read_text().replace('"stop-test"', '"stop-test-b"'))
    harness.env.update(HOME=str(tmp_path / "home"), FAKE_PODMAN_AGENT_S="0", FAKE_PODMAN_STOP_S="1")
    command = [str(LLM_EVAL), "--root", str(harness.root), "run", "--config", str(harness.config),
               "--config", str(second)]
    proc = subprocess.Popen(command, env=harness.env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    harness.processes.append(proc)
    wait_for(lambda: harness.started(["stop", "-t", "60", "llm-eval-server"]))

    proc.send_signal(signal.SIGTERM)

    assert proc.wait(timeout=30) == 130
    assert len([c for c in harness.calls() if c["event"] == "start" and c["argv"][:2] == ["run", "-d"]]) == 1
    assert harness.containers() == []


def assert_guard_stopped_the_run(h: Harness, proc: subprocess.Popen, tripped: float, code: int, phase: str) -> None:
    """The server is dead less than 2 s after the memory became low, and the cleanup removed all containers."""
    assert proc.wait(timeout=30) == code
    killed = h.call_time(["kill", "-s", "KILL", "llm-eval-server"])
    assert killed is not None and killed - tripped < 2
    assert h.ended(["rm", "llm-eval-server"])
    assert h.containers() == []
    assert (h.out / "server.log").exists()
    assert not (h.out / "t1-r1" / "result.json").exists()
    guard = json.loads((h.out / "run.json").read_text())["memory_guard"]
    assert guard["phase"] == phase
    assert "MEMORY GUARD: " in (h.out / "run.log").read_text()


def test_memory_guard_kills_the_server_during_a_trial(harness, tmp_path):
    harness.guard_on_a_fake_host(tmp_path)
    proc = reach(harness, Trial())
    (agent,) = [name for name in harness.containers() if name.startswith("llm-eval-agent-")]

    tripped = harness.set_host(gtt_used_mib=110000, mem_available_mib=30000)  # 2640 MiB free

    assert_guard_stopped_the_run(harness, proc, tripped, cli.GUARD_EXIT, "trial t1-r1")
    assert harness.ended(["rm", "-f", "-t", "10", "--ignore", agent])
    run_log = (harness.out / "run.log").read_text()
    assert "GTT used is 110000 MiB of 112640 MiB, less free than server.gtt_min_margin_mib = 4096 MiB" in run_log
    assert "the memory guard stopped the run of this configuration" in run_log


def test_memory_guard_kills_the_server_during_a_probe_request(harness, tmp_path):
    harness.guard_on_a_fake_host(tmp_path)
    proc = reach(harness, SpeedProbe())  # the request does not get an answer

    tripped = harness.set_host(gtt_used_mib=50000, mem_available_mib=1000)

    assert_guard_stopped_the_run(harness, proc, tripped, cli.GUARD_EXIT, "probes")
    assert ("MemAvailable is 1000 MiB, less than server.mem_available_min_mib = 2048 MiB"
            in (harness.out / "run.log").read_text())


def test_stop_signal_during_the_cleanup_of_the_memory_guard(harness, tmp_path):
    harness.guard_on_a_fake_host(tmp_path)
    harness.env["FAKE_PODMAN_STOP_S"] = "1"
    proc = reach(harness, Trial())
    tripped = harness.set_host(gtt_used_mib=110000, mem_available_mib=30000)
    wait_for(lambda: harness.started(["rm", "-f"]))  # the cleanup of the guard trip removes the agent

    ctrl_c_in_tmux(proc)

    assert_guard_stopped_the_run(harness, proc, tripped, 130, "trial t1-r1")
    assert f"interrupted. To continue: llm-eval run --resume {harness.out}" in (harness.out / "run.log").read_text()


def test_memory_guard_trip_during_the_cleanup_of_a_stop_signal(harness, tmp_path):
    harness.guard_on_a_fake_host(tmp_path)
    harness.env["FAKE_PODMAN_STOP_S"] = "2"
    proc = reach(harness, Trial())
    sigterm(proc)
    wait_for(lambda: harness.started(["rm", "-f"]))  # the cleanup of the stop removes the agent

    tripped = harness.set_host(gtt_used_mib=110000, mem_available_mib=30000)

    assert_guard_stopped_the_run(harness, proc, tripped, 130, "trial t1-r1")
    assert f"interrupted. To continue: llm-eval run --resume {harness.out}" in (harness.out / "run.log").read_text()
