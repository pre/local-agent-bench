"""Hidden tests of hard-py-stockd: restarts at any point give the same results
and the same state as one run without a restart.

The tests use only the command line (README.md). Each "apply" call is a new
process, thus a restart. A run in chunks is compared with one run of the same
commands, and with the expected values of the reference solution in
golden.json (status, reservation and transfer of each result, and the full
JSON report).

STOCKD_WRITE_GOLDEN=<file> writes golden.json instead of a comparison.
"""

import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORK = Path("/work") if Path("/work/stockd").is_dir() else Path.cwd()
GOLDEN_FILE = Path(__file__).with_name("golden.json")
WRITE_GOLDEN = os.environ.get("STOCKD_WRITE_GOLDEN")
_golden_out: dict = {}

WAREHOUSES = ["WH-1", "WH-2", "WH-3"]
SKUS = ["BOLT-M8", "NUT-M8", "PUMP-7", "VALVE-22", "HOSE-3"]
SEGMENT_BYTES = 512
# Changed by the tests that need large segments.
OPTIONS = {"segment_bytes": SEGMENT_BYTES}
RESULT_KEYS = ("status", "reservation", "transfer")


def golden() -> dict:
    if not GOLDEN_FILE.exists():
        return {}
    return json.loads(GOLDEN_FILE.read_text())


def run(code_dir: Path, data: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["STOCKD_FIXED_TIME"] = "2026-11-16T08:00:00Z"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [sys.executable, "-m", "stockd", "--data", str(data), "--segment-bytes", str(OPTIONS["segment_bytes"]), *args]
    proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True, cwd=code_dir, env=env, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(f"stockd {' '.join(args)} exit code {proc.returncode}\n{proc.stderr[-3000:]}")
    return proc


def apply(code_dir: Path, data: Path, cmds: list[dict]) -> list[dict]:
    stdin = "".join(json.dumps(c) + "\n" for c in cmds)
    proc = run(code_dir, data, "apply", "-", stdin=stdin)
    out = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    if len(out) != len(cmds):
        raise AssertionError(f"{len(cmds)} commands but {len(out)} result lines")
    return out


def report(code_dir: Path, data: Path, *extra: str) -> dict:
    return json.loads(run(code_dir, data, "report", "--json", *extra).stdout)


def split(cmds: list[dict], rng: random.Random, chunks: int) -> list[list[dict]]:
    points = sorted(rng.sample(range(1, len(cmds)), chunks - 1))
    return [cmds[a:b] for a, b in zip([0] + points, points + [len(cmds)])]


def generate(seed: int, count: int, kinds: tuple[str, ...], retries: float = 0.0,
             max_lines: int = 4) -> list[dict]:
    """A deterministic random command stream. Some commands are rejected by the service, on purpose."""
    rng = random.Random(seed)
    cmds: list[dict] = []
    reserves = 0
    for i in range(count):
        if cmds and rng.random() < retries:
            old = rng.choice([c for c in cmds if "request_id" in c])
            cmds.append(dict(old))
            continue
        kind = rng.choice(kinds)
        wh, sku = rng.choice(WAREHOUSES), rng.choice(SKUS)
        if kind == "receive":
            lines = [{"sku": rng.choice(SKUS), "qty": rng.randint(1, 30)} for _ in range(rng.randint(1, max_lines))]
            cmd = {"op": "receive", "warehouse": wh, "lines": lines}
        elif kind == "transfer":
            to = rng.choice([w for w in WAREHOUSES if w != wh])
            cmd = {"op": "transfer", "from": wh, "to": to, "sku": sku, "qty": rng.randint(1, 15)}
        elif kind == "adjust":
            cmd = {"op": "adjust", "warehouse": wh, "sku": sku, "delta": rng.choice([-5, -3, -1, 2, 4, 8]),
                   "reason": "count"}
        elif kind == "reserve":
            reserves += 1
            cmd = {"op": "reserve", "warehouse": wh, "sku": sku, "qty": rng.randint(1, 10), "order": f"SO-{i}"}
        else:  # release or ship of a reservation number that may exist
            cmd = {"op": kind, "reservation": rng.randint(1, max(1, reserves))}
        cmd["request_id"] = f"s{seed}-{i}"
        cmds.append(cmd)
    return cmds


class RestartTestCase(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="stockd-hidden-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def check_golden(self, key: str, results: list[dict], state: dict) -> None:
        brief = [{k: r[k] for k in RESULT_KEYS if k in r} for r in results]
        if WRITE_GOLDEN:
            _golden_out[key] = {"results": brief, "report": state}
            return
        expected = golden()[key]
        self.assertEqual(brief, expected["results"], f"{key}: command results differ from the expected results")
        self.assertEqual(state, expected["report"], f"{key}: report differs from the expected report")

    def compare_chunked(self, key: str, cmds: list[dict], seed: int, chunks: int,
                        between=None, prepare=None) -> None:
        """Run cmds once, and in chunks with a restart between them. All must agree."""
        single_dir, chunk_dir = self.tmp / f"{key}-single", self.tmp / f"{key}-chunks"
        if prepare is not None:
            prepare(single_dir)
            prepare(chunk_dir)
        single = apply(WORK, single_dir, cmds)
        single_report = report(WORK, single_dir)
        chunked: list[dict] = []
        parts = split(cmds, random.Random(seed * 7919), chunks)
        for n, part in enumerate(parts):
            chunked += apply(WORK, chunk_dir, part)
            if between is not None and n < len(parts) - 1:
                between(chunk_dir)
        chunked_report = report(WORK, chunk_dir)
        self.check_golden(key, chunked, chunked_report)
        for i, (a, b) in enumerate(zip(single, chunked)):
            self.assertEqual(b, a, f"{key}: command {i + 1} ({cmds[i]['op']}) gives another result after restarts")
        self.assertEqual(chunked_report, single_report, f"{key}: the state after restarts is different")


class MultiEventCommandTest(RestartTestCase):
    """Receives with several lines and transfers, with restarts and segment rotations."""

    def test_streams(self):
        for seed in (11, 12, 13):
            with self.subTest(seed=seed):
                cmds = generate(seed, 120, ("receive", "receive", "transfer", "adjust"))
                self.compare_chunked(f"multi-{seed}", cmds, seed, 7)


class ReservationAfterRestartTest(RestartTestCase):
    """Reservations made before a restart are released and shipped after it."""

    def test_streams(self):
        for seed in (21, 22, 23):
            with self.subTest(seed=seed):
                cmds = generate(seed, 140, ("receive", "receive", "reserve", "reserve", "release", "ship"),
                                max_lines=1)
                self.compare_chunked(f"reservation-{seed}", cmds, seed, 6)

    def test_release_of_reservation_from_before_restart(self):
        data = self.tmp / "data"
        apply(WORK, data, [{"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "PUMP-7", "qty": 40}]}])
        first = apply(WORK, data, [{"op": "reserve", "warehouse": "WH-1", "sku": "PUMP-7", "qty": 10,
                                    "order": "SO-5512"}])
        run(WORK, data, "snapshot")
        after = apply(WORK, data, [{"op": "release", "reservation": first[0]["reservation"]}])
        self.assertEqual(after[0]["status"], "applied")
        self.assertEqual(report(WORK, data)["levels"][0]["available"], 40)


class RetryAfterRestartTest(RestartTestCase):
    """A command that is sent again with the same request ID after a restart is a duplicate."""

    def test_streams(self):
        for seed in (31, 32, 33):
            with self.subTest(seed=seed):
                cmds = generate(seed, 140, ("receive", "receive", "adjust"), retries=0.2, max_lines=1)
                self.compare_chunked(f"retry-{seed}", cmds, seed, 6)

    def test_retry_after_snapshot(self):
        data = self.tmp / "data"
        cmd = {"op": "receive", "request_id": "rcv-881", "warehouse": "WH-1",
               "lines": [{"sku": "BOLT-M8", "qty": 100}]}
        apply(WORK, data, [cmd])
        run(WORK, data, "snapshot")
        self.assertEqual(apply(WORK, data, [cmd])[0]["status"], "duplicate")
        self.assertEqual(report(WORK, data)["levels"][0]["on_hand"], 100)


class RetryWindowTest(RestartTestCase):
    """With a small request_window, the oldest request IDs are forgotten in the same order after restarts."""

    def test_small_window(self):
        def window(data: Path) -> None:
            data.mkdir(parents=True)
            (data / "stockd.toml").write_text("request_window = 6\n")

        for seed in (34, 35):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                cmds: list[dict] = []
                for i in range(160):
                    if i > 12 and rng.random() < 0.35:
                        cmds.append(dict(cmds[i - rng.randint(1, 12)]))
                    else:
                        cmds.append({"op": "receive", "request_id": f"w{seed}-{i}", "warehouse": rng.choice(WAREHOUSES),
                                     "lines": [{"sku": rng.choice(SKUS), "qty": rng.randint(1, 9)}]})
                self.compare_chunked(f"window-{seed}", cmds, seed, 8, prepare=window)


class NonAsciiTest(RestartTestCase):
    """Names with non-ASCII characters in large segments survive the recovery."""

    def setUp(self) -> None:
        super().setUp()
        OPTIONS["segment_bytes"] = 30000

    def tearDown(self) -> None:
        OPTIONS["segment_bytes"] = SEGMENT_BYTES
        super().tearDown()

    def test_streams(self):
        warehouses = ["Lager-Süd", "Склад-Юг", "大阪倉庫"]
        skus = ["MUTTER-M8-Ø", "ボルトM8", "ВЕНТИЛЬ-22", "BOLT-M8"]
        for seed in (71, 72):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                cmds = []
                for i in range(420):
                    wh, sku = rng.choice(warehouses), rng.choice(skus)
                    if rng.random() < 0.7:
                        cmds.append({"op": "receive", "request_id": f"ü{seed}-{i}", "warehouse": wh,
                                     "lines": [{"sku": sku, "qty": rng.randint(1, 20)}]})
                    else:
                        cmds.append({"op": "adjust", "request_id": f"ü{seed}-{i}", "warehouse": wh, "sku": sku,
                                     "delta": rng.choice([-1, 1, 2]), "reason": "棚卸の差異、再確認済み。Bestandsprüfung"})
                self.compare_chunked(f"nonascii-{seed}", cmds, seed, 5)


class MixedRandomTest(RestartTestCase):
    """All commands, retries and restarts together."""

    def test_streams(self):
        kinds = ("receive", "receive", "transfer", "adjust", "reserve", "reserve", "release", "ship")
        for seed in (41, 42, 43, 44):
            with self.subTest(seed=seed):
                cmds = generate(seed, 200, kinds, retries=0.1)
                self.compare_chunked(f"mixed-{seed}", cmds, seed, 9)


class CompactionTest(RestartTestCase):
    """Snapshot and compact between the restarts, as the nightly job does."""

    def test_streams(self):
        kinds = ("receive", "transfer", "adjust", "reserve", "reserve", "release", "ship")
        removed = []

        def nightly(data: Path) -> None:
            before = len(list((data / "segments").iterdir()))
            run(WORK, data, "snapshot")
            run(WORK, data, "compact")
            removed.append(before - len(list((data / "segments").iterdir())))

        for seed in (51, 52):
            with self.subTest(seed=seed):
                cmds = generate(seed, 160, kinds, retries=0.1)
                self.compare_chunked(f"compact-{seed}", cmds, seed, 5, between=nightly)
        self.assertGreater(sum(removed), 0, "compact removed no segments")


class ReplayTest(RestartTestCase):
    """The state from the newest snapshot plus the events is the state from all events."""

    def test_replay_equals_recovery(self):
        kinds = ("receive", "receive", "transfer", "adjust", "reserve", "release", "ship")
        data = self.tmp / "data"
        cmds = generate(61, 200, kinds, retries=0.1)
        for part in split(cmds, random.Random(61), 8):
            apply(WORK, data, part)
            self.assertEqual(json.loads(run(WORK, data, "replay", "--json").stdout), report(WORK, data))


class OldDataDirectoryTest(RestartTestCase):
    """A data directory that the start version of stockd wrote must still load."""

    def baseline_code(self) -> Path:
        baseline = os.environ.get("EVAL_BASELINE")
        if not baseline:
            self.skipTest("EVAL_BASELINE is not set")
        code = self.tmp / "baseline-code"
        code.mkdir()
        archive = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(WORK), "archive", baseline, "stockd"],
                                 capture_output=True, check=True, timeout=60).stdout
        subprocess.run(["tar", "-x", "-C", str(code)], input=archive, check=True, timeout=60)
        return code

    def test_old_data_directory(self):
        old = self.baseline_code()
        data = self.tmp / "data"
        setup = [{"op": "receive", "request_id": f"rcv-{i}", "warehouse": wh, "lines": [{"sku": sku, "qty": 25}]}
                 for i, (wh, sku) in enumerate([(w, s) for w in WAREHOUSES[:2] for s in SKUS])]
        setup += [{"op": "reserve", "request_id": f"res-{i}", "warehouse": "WH-1", "sku": SKUS[i % 3], "qty": 2 + i % 4,
                   "order": f"SO-{900 + i}"} for i in range(12)]
        apply(old, data, setup)
        run(old, data, "snapshot")
        apply(old, data, [{"op": "adjust", "warehouse": "WH-2", "sku": "HOSE-3", "delta": -4, "reason": "count"}])
        later = [{"op": "release", "reservation": 2}, {"op": "ship", "reservation": 11},
                 {"op": "release", "reservation": 10}, {"op": "release", "reservation": 2},
                 {"op": "reserve", "warehouse": "WH-1", "sku": "PUMP-7", "qty": 2, "order": "SO-999"}]
        results = apply(WORK, data, later)
        state = report(WORK, data)
        self.check_golden("old-data", results, state)
        self.assertEqual(json.loads(run(WORK, data, "replay", "--json").stdout), state)


def tearDownModule() -> None:
    if WRITE_GOLDEN:
        Path(WRITE_GOLDEN).write_text(json.dumps(_golden_out, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    unittest.main()
