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
from llm_eval.stop import STOP_SIGNALS, defer_stop_signals, flush_std_streams, notice, start_thread, stop_on_signals


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


def test_signal_in_a_deferred_block_stops_after_the_block():
    done = []
    with stop_on_signals():
        with pytest.raises(KeyboardInterrupt, match="SIGTERM"):
            with defer_stop_signals():
                os.kill(os.getpid(), signal.SIGTERM)
                sum(range(100))
                done.append("block")

    assert done == ["block"]


def test_signal_in_a_deferred_block_of_a_stop_is_dropped():
    with stop_on_signals():
        with pytest.raises(KeyboardInterrupt, match="SIGINT"):
            os.kill(os.getpid(), signal.SIGINT)
        with defer_stop_signals():  # the cleanup after the stop
            os.kill(os.getpid(), signal.SIGTERM)
            sum(range(100))


def test_deferred_block_without_a_signal_does_not_raise():
    with stop_on_signals():
        with defer_stop_signals():
            pass


def test_signal_during_the_installation_of_the_handlers(monkeypatch):
    real_signal = signal.signal
    calls = []

    def signal_with_a_kill(signum, handler):
        calls.append(signum)
        if len(calls) == 1:
            # To the main thread: in the harness the other threads block the stop signals.
            signal.pthread_kill(threading.main_thread().ident, signal.SIGTERM)  # pending until the end
        return real_signal(signum, handler)

    monkeypatch.setattr(signal, "signal", signal_with_a_kill)

    with pytest.raises(KeyboardInterrupt, match="SIGTERM"):
        with stop_on_signals():
            pass

    monkeypatch.undo()
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler
    assert signal.getsignal(signal.SIGHUP) == signal.getsignal(signal.SIGTERM) == signal.SIG_DFL


class ClosedPipe(io.StringIO):
    def write(self, text):
        raise BrokenPipeError(32, "Broken pipe")


def test_notice_writes_run_log_when_stderr_is_a_closed_pipe(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stderr", ClosedPipe())

    notice(tmp_path / "run", "llm-eval: stopping llm-eval-server")

    assert (tmp_path / "run" / "run.log").read_text().endswith(" llm-eval: stopping llm-eval-server\n")


def test_notice_survives_a_run_log_that_cannot_be_written(tmp_path, capsys):
    (tmp_path / "file").write_text("")

    notice(tmp_path / "file" / "run", "llm-eval: stopping llm-eval-server")  # not a directory

    assert "llm-eval: stopping llm-eval-server" in capsys.readouterr().err


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


def test_flush_std_streams_sends_the_rest_of_a_closed_pipe_to_dev_null(monkeypatch):
    read_end, write_end = os.pipe()
    os.close(read_end)  # tee stopped
    stream = open(write_end, "w")
    stream.write("buffered text")
    monkeypatch.setattr("sys.stdout", stream)

    flush_std_streams()

    stream.close()  # the rest goes to /dev/null, no BrokenPipeError
