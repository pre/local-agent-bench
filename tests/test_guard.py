"""The memory guard: a thread that kills the managed server when the memory is almost full."""

import time
from pathlib import Path
from unittest.mock import ANY

import pytest

from fakes import FakePodman
from llm_eval.config import ManagedConfig
from llm_eval.guard import MemoryGuard
from llm_eval.sampler import read_mem_available_mib
from llm_eval.stop import GuardStop, defer_stop_signals, stop_on_signals
from test_sampler import FakeHost, host  # noqa: F401  (fixture)

NAME = "llm-eval-server"
KILL = ["kill", "-s", "KILL", NAME]


class Readings:
    """The values of the fake readers. A value that is an exception is raised."""

    def __init__(self):
        self.values = {"gtt_used": 50000, "gtt_total": 112640, "mem_available": 30000}

    def reader(self, name: str):
        def read() -> int:
            value = self.values[name]
            if isinstance(value, Exception):
                raise value
            return value

        return read


def server_podman() -> FakePodman:
    podman = FakePodman()
    podman.containers[NAME] = {"labels": {"llm-eval.role": "server"}, "running": True}
    return podman


def make_guard(tmp_path: Path, podman, readings: Readings, margin=4096, minimum=2048) -> MemoryGuard:
    cfg = ManagedConfig(image="example.org/llama@sha256:abc", models_dir=tmp_path, model_file="m.gguf", port=1,
                        gtt_min_margin_mib=margin, mem_available_min_mib=minimum)
    return MemoryGuard(podman, tmp_path / "run", cfg, lambda: "trial t1-r1", readings.reader("gtt_used"),
                       readings.reader("gtt_total"), readings.reader("mem_available"), interval_s=0.01)


def run_log(tmp_path: Path) -> str:
    path = tmp_path / "run" / "run.log"
    return path.read_text() if path.exists() else ""


def wait_for(condition, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not condition():
        assert time.monotonic() < deadline, "timeout"
        time.sleep(0.01)


def test_guard_kills_the_server_when_the_gtt_margin_is_lost(tmp_path, capsys):
    podman, readings = server_podman(), Readings()
    guard = make_guard(tmp_path, podman, readings)
    with stop_on_signals():
        guard.start()
        try:
            time.sleep(0.1)
            assert podman.calls == []
            readings.values["gtt_used"] = 109000
            lost = time.monotonic()
            with pytest.raises(GuardStop):
                time.sleep(5)  # the main thread waits, for example for the agent container
            stopped = time.monotonic()
        finally:
            guard.stop()

    assert stopped - lost < 2
    assert podman.calls == [KILL]
    assert podman.containers[NAME]["running"] is False
    assert guard.trip == {"reason": "gtt_margin", "limit_mib": 4096, "gtt_used_mib": 109000, "gtt_total_mib": 112640,
                          "mem_available_mib": 30000, "phase": "trial t1-r1", "time": ANY}
    message = ("llm-eval: MEMORY GUARD: GTT used is 109000 MiB of 112640 MiB, less free than"
               " server.gtt_min_margin_mib = 4096 MiB (trial t1-r1). The harness killed llm-eval-server.")
    assert message in run_log(tmp_path)
    assert message in capsys.readouterr().err


def test_guard_kills_the_server_also_when_the_main_thread_does_not_stop(tmp_path):
    podman, readings = server_podman(), Readings()
    guard = make_guard(tmp_path, podman, readings)
    with stop_on_signals():
        guard.start()
        try:
            with pytest.raises(GuardStop):
                with defer_stop_signals():  # for example the removal of an agent container
                    readings.values["mem_available"] = 2047
                    wait_for(lambda: KILL in podman.calls)
        finally:
            guard.stop()

    assert guard.trip["reason"] == "mem_available"
    assert guard.trip["limit_mib"] == 2048
    assert ("MEMORY GUARD: MemAvailable is 2047 MiB, less than server.mem_available_min_mib = 2048 MiB"
            in run_log(tmp_path))


def test_guard_does_not_trip_at_the_limits(tmp_path):
    podman, readings = server_podman(), Readings()
    readings.values.update(gtt_used=112640 - 4096, mem_available=2048)
    guard = make_guard(tmp_path, podman, readings)
    with stop_on_signals():
        guard.start()
        time.sleep(0.1)
        guard.stop()

    assert guard.trip is None
    assert podman.calls == []
    assert not guard.thread.is_alive()
    assert run_log(tmp_path) == ""


def test_zero_switches_off_the_mem_available_limit(tmp_path):
    podman, readings = server_podman(), Readings()
    readings.values["mem_available"] = 0
    guard = make_guard(tmp_path, podman, readings, minimum=0)
    with stop_on_signals():
        guard.start()
        time.sleep(0.1)
        guard.stop()

    assert guard.trip is None


def test_unreadable_gtt_gives_one_warning_and_no_trip(tmp_path):
    podman, readings = server_podman(), Readings()
    readings.values["gtt_used"] = OSError(5, "Input/output error")
    guard = make_guard(tmp_path, podman, readings)
    with stop_on_signals():
        guard.start()
        try:
            time.sleep(0.1)
            assert podman.calls == []
            readings.values["mem_available"] = 1000  # the other condition still works
            with pytest.raises(GuardStop):
                time.sleep(5)
        finally:
            guard.stop()

    log = run_log(tmp_path)
    assert log.count("WARNING") == 1
    assert "the memory guard cannot read a memory value: [Errno 5] Input/output error" in log
    assert guard.trip["reason"] == "mem_available"
    assert guard.trip["gtt_used_mib"] is None


def test_read_mem_available(host):
    assert read_mem_available_mib(host.root / "meminfo") == 2000


def test_stop_of_a_guard_that_did_not_start(tmp_path):
    guard = make_guard(tmp_path, server_podman(), Readings())

    guard.stop()  # a stop signal came between the creation of the guard and its start

    assert guard.trip is None
