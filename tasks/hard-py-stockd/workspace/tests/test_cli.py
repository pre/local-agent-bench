import json
import unittest

from .helpers import TempDirTest, commands, results, run_cli


class CliTest(TempDirTest):
    def test_apply_and_report(self):
        data = self.tmp / "data"
        proc = run_cli(data, "apply", "-", stdin=commands(
            {"op": "receive", "request_id": "r1", "warehouse": "WH-1",
             "lines": [{"sku": "A", "qty": 10}, {"sku": "B", "qty": 4}]},
            {"op": "reserve", "request_id": "r2", "warehouse": "WH-1", "sku": "A", "qty": 3, "order": "SO-1"},
            {"op": "transfer", "request_id": "r3", "from": "WH-1", "to": "WH-2", "sku": "B", "qty": 4},
        ))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(results(proc), [
            {"request_id": "r1", "seq": 2, "status": "applied"},
            {"request_id": "r2", "reservation": 1, "seq": 3, "status": "applied"},
            {"request_id": "r3", "seq": 5, "status": "applied", "transfer": 1},
        ])
        proc = run_cli(data, "report")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines(), [
            "WAREHOUSE  SKU  ON_HAND  RESERVED  AVAILABLE",
            "WH-1       A         10         3          7",
            "WH-1       B          0         0          0",
            "WH-2       B          4         0          4",
            "1 open reservation(s)",
        ])

    def test_report_json(self):
        data = self.tmp / "data"
        run_cli(data, "apply", "-", stdin=commands(
            {"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 10}]},
            {"op": "reserve", "warehouse": "WH-1", "sku": "A", "qty": 3, "order": "SO-1"},
        ))
        proc = run_cli(data, "report", "--json")
        self.assertEqual(json.loads(proc.stdout), {
            "levels": [{"warehouse": "WH-1", "sku": "A", "on_hand": 10, "reserved": 3, "available": 7}],
            "reservations": [{"id": 1, "warehouse": "WH-1", "sku": "A", "qty": 3, "order": "SO-1"}],
        })

    def test_bad_lines_are_rejected(self):
        proc = run_cli(self.tmp / "data", "apply", "-", stdin='not json\n{"op":"explode"}\n')
        self.assertEqual([r["status"] for r in results(proc)], ["rejected", "rejected"])

    def test_replay_without_snapshots(self):
        data = self.tmp / "data"
        run_cli(data, "apply", "-", stdin=commands(
            {"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 10}]}), segment_bytes=256)
        run_cli(data, "snapshot")
        run_cli(data, "apply", "-", stdin=commands(
            {"op": "adjust", "warehouse": "WH-1", "sku": "A", "delta": 2, "reason": "found"}))
        self.assertEqual(run_cli(data, "replay").stdout, run_cli(data, "report").stdout)

    def test_compact(self):
        data = self.tmp / "data"
        lines = [{"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": n}]} for n in range(1, 21)]
        run_cli(data, "apply", "-", stdin=commands(*lines), segment_bytes=256)
        segments_before = len(list((data / "segments").iterdir()))
        self.assertEqual(run_cli(data, "snapshot", segment_bytes=256).returncode, 0)
        proc = run_cli(data, "compact", segment_bytes=256)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertLess(len(list((data / "segments").iterdir())), segments_before)
        report = json.loads(run_cli(data, "report", "--json").stdout)
        self.assertEqual(report["levels"][0]["on_hand"], sum(range(1, 21)))

    def test_check_log(self):
        data = self.tmp / "data"
        run_cli(data, "apply", "-", stdin=commands(
            {"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 10}]}))
        proc = run_cli(data, "check-log")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("events 1", proc.stdout)


if __name__ == "__main__":
    unittest.main()
