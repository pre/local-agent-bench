"""Stop signals of a run, and messages that a closed stderr or a full disk does not stop.

Ctrl-C in tmux sends SIGINT to all processes of the pane, also to `tee`. Then
the pane closes and tmux sends SIGHUP. A stop with `kill` sends SIGTERM. Each of
the three signals stops the run: the harness then stops and removes its
containers, and more signals do not interrupt this cleanup.
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
RESEND_S = 0.1


class _State:
    stopping = False  # a KeyboardInterrupt of a stop signal is on its way: more signals do nothing
    deferring = 0  # the depth of defer_stop_signals blocks
    deferred: int | None = None  # the first stop signal of a defer_stop_signals block


def _stop(signum, frame) -> None:
    if _State.stopping:
        return
    if _State.deferring:
        _State.deferred = _State.deferred or signum
        return
    _State.stopping = True
    raise KeyboardInterrupt(signal.Signals(signum).name)


def _unraisable(args) -> None:
    """Python ignores an exception that occurs in a deallocator (__del__), also the
    KeyboardInterrupt of _stop, and gives it to this hook. Send the signal again
    after RESEND_S, when the main thread is out of the deallocator."""
    if _State.stopping and isinstance(args.exc_value, KeyboardInterrupt):
        _State.stopping = False
        again = signal.Signals[args.exc_value.args[0]]
        start_thread(threading.Timer(RESEND_S, os.kill, (os.getpid(), again)))
    _State.previous_hook(args)


@contextmanager
def _signals_blocked() -> Iterator[None]:
    """A stop signal stays pending until the end of the block."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, STOP_SIGNALS)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


@contextmanager
def stop_on_signals() -> Iterator[None]:
    """A stop signal raises KeyboardInterrupt. More stop signals do not raise, so
    that they do not interrupt the cleanup. A signal during the change of the
    handlers stays pending until all handlers are changed."""
    previous = {s: signal.getsignal(s) for s in STOP_SIGNALS}
    try:
        with _signals_blocked():
            for s, handler in previous.items():
                if handler is not signal.SIG_IGN:  # nohup, or a background job of a shell script
                    signal.signal(s, _stop)
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
    the block and no stop was on its way, KeyboardInterrupt comes after the block."""
    _State.deferring += 1
    try:
        yield
    finally:
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
