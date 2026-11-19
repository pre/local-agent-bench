import unittest

from stockd.events import draft
from stockd.projection import Inventory


def apply_all(inv: Inventory, *drafts) -> Inventory:
    for seq, d in enumerate(drafts, start=inv.applied_seq + 1):
        inv.apply(d.at(seq, "2026-11-16T08:00:00Z"))
    return inv


class InventoryTest(unittest.TestCase):
    def test_receive_reserve_ship(self):
        inv = apply_all(Inventory(),
                        draft("Received", warehouse="WH-1", sku="A", qty=10),
                        draft("Reserved", reservation=1, warehouse="WH-1", sku="A", qty=4, order="SO-1"),
                        draft("Shipped", reservation=1))
        level = inv.peek("WH-1", "A")
        self.assertEqual((level.on_hand, level.reserved, level.available), (6, 0, 6))
        self.assertEqual(inv.reservations, {})
        self.assertEqual(inv.applied_seq, 3)

    def test_release(self):
        inv = apply_all(Inventory(),
                        draft("Received", warehouse="WH-1", sku="A", qty=10),
                        draft("Reserved", reservation=1, warehouse="WH-1", sku="A", qty=4, order="SO-1"),
                        draft("Released", reservation=1))
        self.assertEqual(inv.peek("WH-1", "A").available, 10)

    def test_transfer(self):
        inv = apply_all(Inventory(),
                        draft("Received", warehouse="WH-1", sku="A", qty=10),
                        draft("TransferredOut", transfer=1, warehouse="WH-1", sku="A", qty=3),
                        draft("TransferredIn", transfer=1, warehouse="WH-2", sku="A", qty=3))
        self.assertEqual(inv.peek("WH-1", "A").on_hand, 7)
        self.assertEqual(inv.peek("WH-2", "A").on_hand, 3)
        self.assertEqual(inv.next_transfer, 2)

    def test_next_reservation_follows_events(self):
        inv = apply_all(Inventory(),
                        draft("Received", warehouse="WH-1", sku="A", qty=10),
                        draft("Reserved", reservation=7, warehouse="WH-1", sku="A", qty=1, order="SO-1"))
        self.assertEqual(inv.next_reservation, 8)

    def test_peek_does_not_add_rows(self):
        inv = Inventory()
        self.assertEqual(inv.peek("WH-9", "Z").available, 0)
        self.assertEqual(inv.rows(), [])

    def test_dict_round_trip_of_levels(self):
        inv = apply_all(Inventory(),
                        draft("Received", warehouse="WH-1", sku="A", qty=10),
                        draft("Received", warehouse="WH-2", sku="B", qty=5),
                        draft("Adjusted", warehouse="WH-2", sku="B", delta=-1, reason="damaged"))
        copy = Inventory.from_dict(inv.to_dict())
        self.assertEqual(copy.rows(), inv.rows())
        self.assertEqual(copy.next_transfer, inv.next_transfer)


if __name__ == "__main__":
    unittest.main()
