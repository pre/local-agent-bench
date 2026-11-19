import json
import unittest

from stockd.clock import FixedClock
from stockd.config import load_config
from stockd.service import InventoryService

from .helpers import TempDirTest


class ServiceTest(TempDirTest):
    def open_service(self, **overrides) -> InventoryService:
        svc = InventoryService(load_config(self.tmp / "data", overrides), FixedClock("2026-11-16T08:00:00Z"))
        self.addCleanup(svc.close)
        return svc

    def stock(self, svc: InventoryService, warehouse: str, sku: str) -> tuple[int, int]:
        level = svc.inventory.peek(warehouse, sku)
        return level.on_hand, level.reserved

    def test_receive_with_packs(self):
        (self.tmp / "data").mkdir()
        (self.tmp / "data" / "catalog.json").write_text(json.dumps({"skus": {"BOLT-M8": {"pack": 50}}}))
        svc = self.open_service()
        result = svc.execute({"op": "receive", "request_id": "r1", "warehouse": "WH-1",
                              "lines": [{"sku": "BOLT-M8", "packs": 3}, {"sku": "NUT-M8", "qty": 7}]})
        self.assertEqual(result, {"request_id": "r1", "status": "applied", "seq": 2})
        self.assertEqual(self.stock(svc, "WH-1", "BOLT-M8"), (150, 0))
        self.assertEqual(self.stock(svc, "WH-1", "NUT-M8"), (7, 0))

    def test_packs_without_catalogue_entry(self):
        svc = self.open_service()
        result = svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "X", "packs": 1}]})
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(svc.store.last_seq, 0)

    def test_reserve_needs_available_stock(self):
        svc = self.open_service()
        svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 5}]})
        first = svc.execute({"op": "reserve", "warehouse": "WH-1", "sku": "A", "qty": 4, "order": "SO-1"})
        second = svc.execute({"op": "reserve", "warehouse": "WH-1", "sku": "A", "qty": 2, "order": "SO-2"})
        self.assertEqual(first["reservation"], 1)
        self.assertEqual(second["status"], "rejected")
        self.assertEqual(self.stock(svc, "WH-1", "A"), (5, 4))

    def test_release_and_ship(self):
        svc = self.open_service()
        svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 5}]})
        svc.execute({"op": "reserve", "warehouse": "WH-1", "sku": "A", "qty": 2, "order": "SO-1"})
        svc.execute({"op": "reserve", "warehouse": "WH-1", "sku": "A", "qty": 1, "order": "SO-2"})
        self.assertEqual(svc.execute({"op": "release", "reservation": 1})["status"], "applied")
        self.assertEqual(svc.execute({"op": "release", "reservation": 1})["status"], "ignored")
        self.assertEqual(svc.execute({"op": "ship", "reservation": 2})["status"], "applied")
        self.assertEqual(svc.execute({"op": "ship", "reservation": 2})["status"], "rejected")
        self.assertEqual(self.stock(svc, "WH-1", "A"), (4, 0))

    def test_adjust_cannot_go_below_reserved(self):
        svc = self.open_service()
        svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 5}]})
        svc.execute({"op": "reserve", "warehouse": "WH-1", "sku": "A", "qty": 3, "order": "SO-1"})
        bad = svc.execute({"op": "adjust", "warehouse": "WH-1", "sku": "A", "delta": -3, "reason": "count"})
        good = svc.execute({"op": "adjust", "warehouse": "WH-1", "sku": "A", "delta": -2, "reason": "count"})
        self.assertEqual((bad["status"], good["status"]), ("rejected", "applied"))
        self.assertEqual(self.stock(svc, "WH-1", "A"), (3, 3))

    def test_transfer(self):
        svc = self.open_service()
        svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 5}]})
        result = svc.execute({"op": "transfer", "from": "WH-1", "to": "WH-2", "sku": "A", "qty": 5})
        self.assertEqual(result, {"request_id": None, "status": "applied", "seq": 3, "transfer": 1})
        self.assertEqual(self.stock(svc, "WH-1", "A"), (0, 0))
        self.assertEqual(self.stock(svc, "WH-2", "A"), (5, 0))

    def test_duplicate_request(self):
        svc = self.open_service()
        cmd = {"op": "receive", "request_id": "rcv-1", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 5}]}
        self.assertEqual(svc.execute(cmd)["status"], "applied")
        self.assertEqual(svc.execute(cmd), {"request_id": "rcv-1", "status": "duplicate"})
        self.assertEqual(self.stock(svc, "WH-1", "A"), (5, 0))

    def test_rejected_request_can_be_sent_again(self):
        svc = self.open_service()
        cmd = {"op": "reserve", "request_id": "res-1", "warehouse": "WH-1", "sku": "A", "qty": 1, "order": "SO-1"}
        self.assertEqual(svc.execute(cmd)["status"], "rejected")
        svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 1}]})
        self.assertEqual(svc.execute(cmd)["status"], "applied")


class RestartTest(TempDirTest):
    def open_service(self) -> InventoryService:
        return InventoryService(load_config(self.tmp / "data"), FixedClock("2026-11-16T08:00:00Z"))

    def test_state_after_restart(self):
        with self.open_service() as svc:
            svc.execute({"op": "receive", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 5}]})
            svc.execute({"op": "reserve", "warehouse": "WH-1", "sku": "A", "qty": 2, "order": "SO-1"})
            before = svc.inventory.rows()
        with self.open_service() as svc:
            self.assertEqual(svc.inventory.rows(), before)
            self.assertEqual(svc.recovery.replayed, 2)

    def test_retry_after_restart_is_a_duplicate(self):
        cmd = {"op": "receive", "request_id": "rcv-9", "warehouse": "WH-1", "lines": [{"sku": "A", "qty": 5}]}
        with self.open_service() as svc:
            svc.execute(cmd)
        with self.open_service() as svc:
            self.assertEqual(svc.execute(cmd)["status"], "duplicate")
            self.assertEqual(svc.inventory.peek("WH-1", "A").on_hand, 5)


if __name__ == "__main__":
    unittest.main()
