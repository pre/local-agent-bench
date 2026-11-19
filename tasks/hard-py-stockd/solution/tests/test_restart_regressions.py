import unittest

from stockd.clock import FixedClock
from stockd.config import load_config
from stockd.service import InventoryService

from .helpers import TempDirTest


class RestartRegressionTest(TempDirTest):
    def open_service(self, **overrides) -> InventoryService:
        return InventoryService(load_config(self.tmp / "data", overrides), FixedClock("2026-11-16T08:00:00Z"))

    def test_rotation_inside_a_command(self):
        # Small segments: the store closes segments between the two events of transfers.
        with self.open_service(segment_max_bytes=256) as svc:
            svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 100}]})
            for _ in range(12):
                svc.execute({"op": "transfer", "from": "WH-1", "to": "WH-2", "sku": "A", "qty": 1})
            before = svc.inventory.rows()
        with self.open_service(segment_max_bytes=256) as svc:
            self.assertIsNotNone(svc.recovery.snapshot_seq)
            self.assertEqual(svc.inventory.rows(), before)

    def test_release_after_snapshot(self):
        with self.open_service() as svc:
            svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 10}]})
            number = svc.execute({"op": "reserve", "warehouse": "WH-1", "sku": "A", "qty": 4,
                                  "order": "SO-1"})["reservation"]
            svc.snapshot()
        with self.open_service() as svc:
            self.assertEqual(svc.execute({"op": "release", "reservation": number})["status"], "applied")
            self.assertEqual(svc.inventory.peek("WH-1", "A").available, 10)

    def test_retry_after_snapshot(self):
        cmd = {"op": "receive", "request_id": "rcv-1", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 5}]}
        with self.open_service() as svc:
            svc.execute(cmd)
            svc.snapshot()
        with self.open_service() as svc:
            self.assertEqual(svc.execute(cmd)["status"], "duplicate")
            self.assertEqual(svc.inventory.peek("WH-1", "A").on_hand, 5)


if __name__ == "__main__":
    unittest.main()
