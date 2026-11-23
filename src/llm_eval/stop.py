"""Stop signals of a run, and messages that a closed stderr or a full disk does not stop.

Ctrl-C in tmux sends SIGINT to all processes of the pane, also to `tee`. Then
the pane closes and tmux sends SIGHUP. A stop with `kill` sends SIGTERM. Each of
the three signals stops the run: the harness then stops and removes its
containers, and more signals do not interrupt this cleanup.

The memory guard (guard.py) sends GUARD_SIGNAL to the main thread. It raises
GuardStop: the run of one configuration stops, with the same cleanup. A stop
signal does not interrupt this cleanup either. It raises KeyboardInterrupt at
end_guard_stop(), after the cleanup.
"""

import os
import signal
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
GUARD_SIGNAL = signal.SIGUSR1
RESEND_S = 0.1


class GuardStop(BaseException):
    """The memory guard killed the server. As for KeyboardInterrupt, `except
    Exception` does not catch it: the trial in progress gets no result."""


class _State:
    stopping = False  # a KeyboardInterrupt of a stop signal is on its way: more signals do nothing
    deferring = 0  # the depth of defer_stop_signals blocks
    deferred: int | None = None  # the first stop signal of a defer_stop_signals block, else the guard signal


def _stop(signum, frame) -> None:
    if _State.stopping:
        return
    if _State.deferring:
        if _State.deferred in (None, GUARD_SIGNAL):
            _State.deferred = signum
        return
    if signum == GUARD_SIGNAL:
        _State.deferring += 1  # the cleanup of the guard stop is a defer block until end_guard_stop()
        raise GuardStop
    _State.stopping = True
    raise KeyboardInterrupt(signal.Signals(signum).name)


def send_guard_signal() -> None:
    """Make the main thread raise GuardStop, also in a blocking call."""
    signal.pthread_kill(threading.main_thread().ident, GUARD_SIGNAL)


def end_guard_stop() -> None:
    """Call it when the cleanup of a GuardStop is complete. A stop signal that came
    during the cleanup then raises KeyboardInterrupt."""
    _end_deferring()


def _unraisable(args) -> None:
    """Python ignores an exception that occurs in a deallocator (__del__), also the
    KeyboardInterrupt of _stop, and gives it to this hook. Send the signal again
    after RESEND_S, when the main thread is out of the deallocator."""
    if isinstance(args.exc_value, GuardStop):
        _State.deferring -= 1  # the cleanup of the lost GuardStop does not occur
        start_thread(threading.Timer(RESEND_S, send_guard_signal))
    elif _State.stopping and isinstance(args.exc_value, KeyboardInterrupt):
        _State.stopping = False
        again = signal.Signals[args.exc_value.args[0]]
        start_thread(threading.Timer(RESEND_S, os.kill, (os.getpid(), again)))
    _State.previous_hook(args)


@contextmanager
def _signals_blocked() -> Iterator[None]:
    """A stop signal stays pending until the end of the block. Python runs a pending
    handler after it changes the mask: when the handler raises, the finally
    clause must restore the mask, thus the change is in the try clause."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, [])
    try:
        signal.pthread_sigmask(signal.SIG_BLOCK, STOP_SIGNALS)
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


@contextmanager
def stop_on_signals() -> Iterator[None]:
    """A stop signal raises KeyboardInterrupt. More stop signals do not raise, so
    that they do not interrupt the cleanup. A signal during the change of the
    handlers stays pending until all handlers are changed. The guard signal
    raises GuardStop."""
    previous = {s: signal.getsignal(s) for s in (*STOP_SIGNALS, GUARD_SIGNAL)}
    try:
        with _signals_blocked():
            for s in STOP_SIGNALS:
                if previous[s] is not signal.SIG_IGN:  # nohup, or a background job of a shell script
                    signal.signal(s, _stop)
            signal.signal(GUARD_SIGNAL, _stop)  # also when ignored: the memory guard of the harness sends it
            _State.previous_hook, sys.unraisablehook = sys.unraisablehook, _unraisable
        yield
    finally:
        with _signals_blocked():
            sys.unraisablehook = _State.previous_hook
            for s, handler in previous.items():
                signal.signal(s, handler)
            _State.stopping, _State.deferring, _State.deferred = False, 0, None


@contextmanager
def defer_stop_signals() -> Iterator[None]:
    """A stop signal does not interrupt the block. When a stop signal came during
    the block and no stop was on its way, KeyboardInterrupt comes after the block.
    When only the guard signal came, GuardStop comes after the block."""
    _State.deferring += 1
    try:
        yield
    finally:
        _end_deferring()


def _end_deferring() -> None:
    _State.deferring -= 1
    if not _State.deferring and _State.deferred:
        signum, _State.deferred = _State.deferred, None
        _stop(signum, None)


def start_thread(thread: threading.Thread) -> None:
    """Start a thread that blocks the stop signals. The kernel gives a signal of the
    process to one thread that does not block it. Only the main thread then gets
    it, and a blocking call of the main thread (for example a probe request that
    waits up to 1800 s) stops at once."""
    with _signals_blocked():
        thread.start()  # the new thread gets the signal mask of this thread


def notice(out_dir: Path, text: str) -> None:
    """Write a line to stderr and to run.log of the run directory. A failed write
    (a closed pipe of stderr, a full disk) does not stop the harness."""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / "run.log").open("a") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {text}\n")
    except OSError:
        pass
    try:
        print(text, file=sys.stderr, flush=True)
    except OSError:
        pass


def flush_std_streams() -> None:
    """Flush stdout and stderr. When the reader of a stream stopped (Ctrl-C also
    stops `tee`), send the rest to /dev/null: else the flush at the exit of
    Python fails, and the exit code is 120."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except OSError:
            os.dup2(os.open(os.devnull, os.O_WRONLY), stream.fileno())
