"""Memory of the host during a trial: GTT used, MemAvailable, SwapFree and memory pressure.

The sampler runs in a thread of the harness and reads /sys and /proc of the host.
"""

import csv
import glob
import threading
from datetime import datetime, timezone
from pathlib import Path

GTT_PATTERN = "/sys/class/drm/card*/device/mem_info_gtt_used"
COLUMNS = ["time", "gtt_used_mib", "mem_available_mib", "swap_free_mib", "psi_some_avg10", "psi_full_avg10"]


def read_gtt_used_mib(pattern: str = GTT_PATTERN) -> int:
    """GTT used of all GPUs. 0 when there is no GPU."""
    return sum(int(Path(p).read_text()) for p in glob.glob(pattern)) >> 20


def read_meminfo_mib(path: Path, *keys: str) -> list[int]:
    values = {}
    for line in path.read_text().splitlines():
        key, _, rest = line.partition(":")
        values[key] = int(rest.split()[0]) >> 10
    return [values[key] for key in keys]


def read_pressure_avg10(path: Path) -> list[float]:
    """The avg10 values of the "some" and "full" lines of /proc/pressure/memory."""
    values = {}
    for line in path.read_text().splitlines():
        kind, *fields = line.split()
        values[kind] = float(dict(f.split("=") for f in fields)["avg10"])
    return [values["some"], values["full"]]


class MemorySampler:
    """Trial observer "memory": writes memory.csv in the trial directory."""

    name = "memory"

    def __init__(self, interval_s: float = 1.0, gtt_pattern: str = GTT_PATTERN,
                 meminfo: Path = Path("/proc/meminfo"), pressure: Path = Path("/proc/pressure/memory")):
        self.interval_s = interval_s
        self.gtt_pattern = gtt_pattern
        self.meminfo = meminfo
        self.pressure = pressure

    def start(self, trial_dir: Path) -> None:
        self.rows: list[list] = []
        self.file = (trial_dir / "memory.csv").open("w", newline="")
        self.writer = csv.writer(self.file)
        self.writer.writerow(COLUMNS)
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self) -> dict:
        self.stopping.set()
        self.thread.join()
        self._sample()
        self.file.close()
        gtt, available, swap, some, full = (list(column) for column in zip(*self.rows))
        return {
            "gtt_used_start_mib": gtt[0],
            "gtt_used_peak_mib": max(gtt),
            "mem_available_min_mib": min(available),
            "swap_free_min_mib": min(swap),
            "psi_some_avg10_max": max(some),
            "psi_full_avg10_max": max(full),
            "samples": len(self.rows),
        }

    def _loop(self) -> None:
        self._sample()
        while not self.stopping.wait(self.interval_s):
            self._sample()

    def _sample(self) -> None:
        row = [
            read_gtt_used_mib(self.gtt_pattern),
            *read_meminfo_mib(self.meminfo, "MemAvailable", "SwapFree"),
            *read_pressure_avg10(self.pressure),
        ]
        self.rows.append(row)
        self.writer.writerow([datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), *row])
        self.file.flush()
