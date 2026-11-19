import csv
import time
from pathlib import Path

import pytest

from llm_eval.sampler import MemorySampler, read_gtt_used_mib

MEMINFO = """MemTotal:       131072000 kB
MemFree:         1000000 kB
MemAvailable:   {avail} kB
SwapTotal:       8388604 kB
SwapFree:       {swap} kB
"""
PRESSURE = """some avg10={some} avg60=0.00 avg300=0.00 total=1
full avg10={full} avg60=0.00 avg300=0.00 total=1
"""


class FakeHost:
    """Files in the format of /sys and /proc that a test can change."""

    def __init__(self, root: Path):
        self.root = root
        for card in ("card0", "card1"):
            (root / card / "device").mkdir(parents=True)
        self.set(gtt_mib=(100, 50), avail_mib=2000, swap_mib=800, some=0.5, full=0.25)

    def set(self, gtt_mib, avail_mib, swap_mib, some, full):
        for card, mib in zip(("card0", "card1"), gtt_mib):
            (self.root / card / "device" / "mem_info_gtt_used").write_text(f"{mib * 1048576}\n")
        (self.root / "meminfo").write_text(MEMINFO.format(avail=avail_mib * 1024, swap=swap_mib * 1024))
        (self.root / "pressure").write_text(PRESSURE.format(some=some, full=full))

    def sampler(self, interval_s=0.01) -> MemorySampler:
        return MemorySampler(interval_s, gtt_pattern=str(self.root / "card*/device/mem_info_gtt_used"),
                             meminfo=self.root / "meminfo", pressure=self.root / "pressure")


@pytest.fixture
def host(tmp_path):
    return FakeHost(tmp_path / "host")


def test_read_gtt_used_sums_the_cards(host):
    assert read_gtt_used_mib(str(host.root / "card*/device/mem_info_gtt_used")) == 150


def test_read_gtt_used_without_cards(tmp_path):
    assert read_gtt_used_mib(str(tmp_path / "card*/x")) == 0


def test_sampler_writes_csv_and_returns_extremes(host, tmp_path):
    trial = tmp_path / "trial"
    trial.mkdir()
    sampler = host.sampler()

    sampler.start(trial)
    time.sleep(0.05)
    host.set(gtt_mib=(300, 50), avail_mib=1500, swap_mib=700, some=3.5, full=1.25)
    time.sleep(0.05)
    host.set(gtt_mib=(200, 50), avail_mib=1800, swap_mib=750, some=1.0, full=0.0)
    summary = sampler.stop()

    assert summary == {
        "gtt_used_start_mib": 150,
        "gtt_used_peak_mib": 350,
        "mem_available_min_mib": 1500,
        "swap_free_min_mib": 700,
        "psi_some_avg10_max": 3.5,
        "psi_full_avg10_max": 1.25,
        "samples": summary["samples"],
    }
    with (trial / "memory.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == summary["samples"] >= 3
    assert list(rows[0]) == ["time", "gtt_used_mib", "mem_available_mib", "swap_free_mib",
                             "psi_some_avg10", "psi_full_avg10"]
    assert rows[0]["time"].endswith("Z")
    assert rows[-1]["gtt_used_mib"] == "250"


def test_sampler_has_samples_when_stopped_at_once(host, tmp_path):
    sampler = host.sampler(interval_s=60)

    sampler.start(tmp_path)
    summary = sampler.stop()

    assert summary["samples"] == 2
    assert sampler.name == "memory"
