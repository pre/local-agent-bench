import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TempDirTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()


def run_cli(data: Path, *args: str, stdin: str | None = None, segment_bytes: int | None = None
            ) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "stockd", "--data", str(data)]
    if segment_bytes is not None:
        cmd += ["--segment-bytes", str(segment_bytes)]
    env = {**os.environ, "STOCKD_FIXED_TIME": "2026-11-16T08:00:00Z"}
    return subprocess.run(cmd + list(args), input=stdin, capture_output=True, text=True, cwd=ROOT, env=env,
                          timeout=60)


def commands(*objs: dict) -> str:
    return "".join(json.dumps(o) + "\n" for o in objs)


def results(proc: subprocess.CompletedProcess) -> list[dict]:
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
