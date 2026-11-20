"""Stop signals of a run, and messages that a closed stderr does not stop.

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


@contextmanager
def stop_on_signals() -> Iterator[None]:
    """A stop signal raises KeyboardInterrupt. More stop signals do not raise, so
    that they do not interrupt the cleanup.

    Python ignores an exception that occurs in a deallocator (__del__), also a
    KeyboardInterrupt of the signal handler, and gives it to sys.unraisablehook.
    The hook then sends the signal again after RESEND_S, when the main thread is
    out of the deallocator."""
    stopping = False

    def stop(signum, frame) -> None:
        nonlocal stopping
        if not stopping:
            stopping = True
            raise KeyboardInterrupt(signal.Signals(signum).name)

    def unraisable(args) -> None:
        nonlocal stopping
        if stopping and isinstance(args.exc_value, KeyboardInterrupt):
            stopping = False
            again = signal.Signals[args.exc_value.args[0]]
            start_thread(threading.Timer(RESEND_S, os.kill, (os.getpid(), again)))
        previous_hook(args)

    previous = {s: signal.getsignal(s) for s in STOP_SIGNALS}
    previous_hook = sys.unraisablehook
    for s, handler in previous.items():
        if handler is not signal.SIG_IGN:  # nohup, or a background job of a shell script
            signal.signal(s, stop)
    sys.unraisablehook = unraisable
    try:
        yield
    finally:
        sys.unraisablehook = previous_hook
        for s, handler in previous.items():
            signal.signal(s, handler)


@contextmanager
def ignore_stop_signals() -> Iterator[None]:
    previous = {s: signal.signal(s, signal.SIG_IGN) for s in STOP_SIGNALS}
    try:
        yield
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)


def start_thread(thread: threading.Thread) -> None:
    """Start a thread that blocks the stop signals. The kernel gives a signal of the
    process to one thread that does not block it. Only the main thread then gets
    it, and a blocking call of the main thread (for example a probe request that
    waits up to 1800 s) stops at once."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, STOP_SIGNALS)
    try:
        thread.start()  # the new thread gets the signal mask of this thread
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def notice(out_dir: Path, text: str) -> None:
    """Write a line to stderr and to run.log of the run directory. When the reader
    of stderr stopped (a closed pipe), only run.log gets the line."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "run.log").open("a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {text}\n")
    try:
        print(text, file=sys.stderr, flush=True)
    except OSError:
        pass
