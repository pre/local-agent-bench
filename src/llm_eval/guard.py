"""The memory guard of a managed server.

A full GTT stops the desktop of the host. Thus a thread reads GTT used, GTT
total and MemAvailable each second, from the time the server is healthy until
the harness stops it. When GTT total minus GTT used is less than
server.gtt_min_margin_mib, or MemAvailable is less than
server.mem_available_min_mib, the guard:

1. sends the guard signal to the main thread (see stop.py). The main thread then
   raises GuardStop, also in a blocking call, and removes the agent container and
   the server as after a stop signal.
2. kills the server container at once. This does not wait for the main thread.
3. writes the values to stderr and run.log.
"""

import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .config import MANAGED_CONTAINER, ManagedConfig
from .stop import notice, send_guard_signal, start_thread

GUARD_INTERVAL_S = 1.0

Reader = Callable[[], int]


def trip_condition(trip: dict) -> str:
    """The condition of a trip with its values."""
    if trip["reason"] == "gtt_margin":
        return (f"GTT used is {trip['gtt_used_mib']} MiB of {trip['gtt_total_mib']} MiB, less free than"
                f" server.gtt_min_margin_mib = {trip['limit_mib']} MiB")
    return (f"MemAvailable is {trip['mem_available_mib']} MiB, less than"
            f" server.mem_available_min_mib = {trip['limit_mib']} MiB")


class MemoryGuard:
    """After a trip, `trip` has the values for run.json, else it is None."""

    def __init__(self, podman, out_dir: Path, cfg: ManagedConfig, phase: Callable[[], str], gtt_used: Reader,
                 gtt_total: Reader, mem_available: Reader, interval_s: float = GUARD_INTERVAL_S):
        self.podman = podman
        self.out_dir = out_dir
        self.cfg = cfg
        self.phase = phase
        self.readers = (gtt_used, gtt_total, mem_available)
        self.interval_s = interval_s
        self.trip: dict | None = None
        self.warned = False
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        start_thread(self.thread)

    def stop(self) -> None:
        self.stopping.set()
        self.thread.join()

    def _loop(self) -> None:
        while True:
            self.trip = self._check()
            if self.trip:
                send_guard_signal()
                self.podman.call(["kill", "-s", "KILL", MANAGED_CONTAINER])
                notice(self.out_dir, f"llm-eval: MEMORY GUARD: {trip_condition(self.trip)} ({self.trip['phase']})."
                                     f" The harness killed {MANAGED_CONTAINER}.")
                return
            if self.stopping.wait(self.interval_s):
                return

    def _check(self) -> dict | None:
        """Return the values of a trip, or None when the memory is sufficient."""
        used, total, available = (self._read(read) for read in self.readers)
        if used is not None and total is not None and total - used < self.cfg.gtt_min_margin_mib:
            reason, limit = "gtt_margin", self.cfg.gtt_min_margin_mib
        elif available is not None and available < self.cfg.mem_available_min_mib:
            reason, limit = "mem_available", self.cfg.mem_available_min_mib
        else:
            return None
        return {"reason": reason, "limit_mib": limit, "gtt_used_mib": used, "gtt_total_mib": total,
                "mem_available_mib": available, "phase": self.phase(),
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    def _read(self, read: Reader) -> int | None:
        """A value that cannot be read is None: it does not trip the guard. The first one gives a warning."""
        try:
            return read()
        except (OSError, ValueError) as e:
            if not self.warned:
                self.warned = True
                notice(self.out_dir, f"llm-eval: WARNING: the memory guard cannot read a memory value: {e}. "
                                     "A value that it cannot read does not stop the server.")
            return None
