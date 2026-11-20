"""Unit tests of stop.py: the stop signals and the messages of the cleanup."""

import io
import os
import signal
import threading
import time
from pathlib import Path

import pytest

from llm_eval.sampler import MemorySampler
from llm_eval.server import UnixRelay
from llm_eval.stop import STOP_SIGNALS, ignore_stop_signals, notice, start_thread, stop_on_signals


def blocked_signals(thread: threading.Thread) -> set[int]:
    status = Path(f"/proc/self/task/{thread.native_id}/status").read_text()
    mask = int(next(line for line in status.splitlines() if line.startswith("SigBlk:")).split()[1], 16)
    return {s for s in STOP_SIGNALS if mask & (1 << (s - 1))}


@pytest.mark.parametrize("first", STOP_SIGNALS)
def test_first_stop_signal_raises_and_later_ones_are_ignored(first):
    with stop_on_signals():
        with pytest.raises(KeyboardInterrupt, match=signal.Signals(first).name):
            os.kill(os.getpid(), first)
        for later in STOP_SIGNALS:
            os.kill(os.getpid(), later)  # no exception, the process continues

    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler
    assert signal.getsignal(signal.SIGHUP) == signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


class SignalInDeallocator:
    """Python ignores an exception of __del__: the KeyboardInterrupt of the signal is lost."""

    def __del__(self):
        os.kill(os.getpid(), signal.SIGHUP)
        sum(range(100))  # the handler runs here, in the deallocator


def test_stop_comes_again_when_a_deallocator_swallowed_it(monkeypatch):
    monkeypatch.setattr("sys.unraisablehook", lambda args: None)  # no "Exception ignored" message
    start = time.monotonic()
    with stop_on_signals():
        with pytest.raises(KeyboardInterrupt, match="SIGHUP"):
            SignalInDeallocator()  # deleted at once
            time.sleep(5)

    assert time.monotonic() - start < 2


def test_an_ignored_signal_stays_ignored(monkeypatch):
    previous = signal.signal(signal.SIGHUP, signal.SIG_IGN)  # nohup
    try:
        with stop_on_signals():
            assert signal.getsignal(signal.SIGHUP) is signal.SIG_IGN
            assert signal.getsignal(signal.SIGTERM) is not signal.SIG_DFL
    finally:
        signal.signal(signal.SIGHUP, previous)


def test_ignore_stop_signals_restores_the_handlers():
    with stop_on_signals():
        with ignore_stop_signals():
            os.kill(os.getpid(), signal.SIGTERM)
            assert all(signal.getsignal(s) is signal.SIG_IGN for s in STOP_SIGNALS)
        with pytest.raises(KeyboardInterrupt):
            os.kill(os.getpid(), signal.SIGTERM)


class ClosedPipe(io.StringIO):
    def write(self, text):
        raise BrokenPipeError(32, "Broken pipe")


def test_notice_writes_run_log_when_stderr_is_a_closed_pipe(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stderr", ClosedPipe())

    notice(tmp_path / "run", "llm-eval: stopping llm-eval-server")

    assert (tmp_path / "run" / "run.log").read_text().endswith(" llm-eval: stopping llm-eval-server\n")


def test_started_thread_does_not_get_the_stop_signals():
    done = threading.Event()
    thread = threading.Thread(target=done.wait, daemon=True)

    start_thread(thread)

    assert blocked_signals(thread) == set(STOP_SIGNALS)
    assert blocked_signals(threading.main_thread()) == set()
    done.set()
    thread.join()


def test_sampler_and_relay_threads_do_not_get_the_stop_signals(tmp_path):
    sampler = MemorySampler(interval_s=0.01)
    sampler.start(tmp_path)
    relay = UnixRelay(tmp_path / "api.sock", "127.0.0.1", 1)
    relay.start()
    try:
        assert blocked_signals(sampler.thread) == set(STOP_SIGNALS)
        assert blocked_signals(relay.thread) == set(STOP_SIGNALS)
    finally:
        relay.stop()
        sampler.stop()
