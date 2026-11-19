import json
import unittest

from stockd.clock import FixedClock
from stockd.config import load_config
from stockd.service import InventoryService

from .helpers import TempDirTest


class SnapshotTest(TempDirTest):
    def open_service(self, **overrides) -> InventoryService:
        return InventoryService(load_config(self.tmp / "data", overrides), FixedClock("2026-11-16T08:00:00Z"))

    def test_recovery_from_snapshot(self):
        with self.open_service() as svc:
            svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 5}]})
            svc.execute({"op": "receive", "warehouse": "WH-2", "lines": [{"sku": "B", "qty": 3}]})
            seq = svc.snapshot()
            svc.execute({"op": "adjust", "warehouse": "WH-1", "sku": "A", "delta": -1, "reason": "count"})
            before = svc.inventory.rows()
        self.assertEqual(seq, 2)
        with self.open_service() as svc:
            self.assertEqual(svc.recovery.snapshot_seq, 2)
            self.assertEqual(svc.recovery.replayed, 1)
            self.assertEqual(svc.inventory.rows(), before)

    def test_snapshot_file(self):
        with self.open_service() as svc:
            svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 5}]})
            svc.snapshot()
        files = sorted((self.tmp / "data" / "snapshots").iterdir())
        self.assertEqual([f.name for f in files], ["snap-000000000001.json"])
        body = json.loads(files[0].read_text())
        self.assertEqual((body["format"], body["seq"]), (1, 1))
        self.assertEqual(body["state"]["levels"], {"WH-1": {"A": [5, 0]}})

    def test_snapshots_on_rotation_are_pruned(self):
        with self.open_service(segment_max_bytes=256) as svc:
            for i in range(30):
                svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": i + 1}]})
            on_hand = svc.inventory.peek("WH-1", "A").on_hand
        snapshots = list((self.tmp / "data" / "snapshots").iterdir())
        self.assertEqual(len(snapshots), 2)
        with self.open_service(segment_max_bytes=256) as svc:
            self.assertIsNotNone(svc.recovery.snapshot_seq)
            self.assertEqual(svc.inventory.peek("WH-1", "A").on_hand, on_hand)

    def test_bad_snapshot_falls_back_to_an_older_one(self):
        with self.open_service() as svc:
            svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 5}]})
            svc.snapshot()
            svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 1}]})
            svc.snapshot()
        newest = self.tmp / "data" / "snapshots" / "snap-000000000002.json"
        newest.write_text("{not json")
        with self.open_service() as svc:
            self.assertEqual(svc.recovery.snapshot_seq, 1)
            self.assertEqual(svc.inventory.peek("WH-1", "A").on_hand, 6)


if __name__ == "__main__":
    unittest.main()
