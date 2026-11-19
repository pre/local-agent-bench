import unittest

from stockd.clock import FixedClock
from stockd.errors import StoreError
from stockd.events import draft
from stockd.segments import list_segments
from stockd.store import EventStore

from .helpers import TempDirTest


def receive(qty: int, rid: str | None = None):
    return draft("Received", rid, warehouse="WH-1", sku="BOLT-M8", qty=qty)


class StoreTest(TempDirTest):
    def open_store(self, max_bytes: int = 10_000) -> EventStore:
        store = EventStore(self.tmp / "segments", max_bytes, FixedClock("2026-11-16T08:00:00Z"))
        store.open()
        self.addCleanup(store.close)
        return store

    def test_append_gives_continuous_seqs(self):
        store = self.open_store()
        events = store.append([receive(1), receive(2)]) + store.append([receive(3)])
        self.assertEqual([e.seq for e in events], [1, 2, 3])
        self.assertEqual(store.last_seq, 3)

    def test_reopen_continues(self):
        store = self.open_store()
        store.append([receive(1), receive(2)])
        store.close()
        store = self.open_store()
        self.assertEqual(store.last_seq, 2)
        self.assertEqual(store.append([receive(3)])[0].seq, 3)
        self.assertEqual([e.data["qty"] for e in store.read_from(1)], [1, 2, 3])

    def test_rotation_by_size(self):
        store = self.open_store(max_bytes=300)
        closed = []
        store.add_rotate_listener(closed.append)
        for i in range(10):
            store.append([receive(i + 1)])
        segments = list_segments(self.tmp / "segments")
        self.assertGreater(len(segments), 2)
        self.assertEqual([s.first_seq for s in segments][0], 1)
        self.assertEqual(closed, [s.first_seq - 1 for s in segments[1:]])
        self.assertEqual([e.seq for e in store.read_from(1)], list(range(1, 11)))

    def test_read_from_the_middle(self):
        store = self.open_store(max_bytes=300)
        for i in range(10):
            store.append([receive(i + 1)])
        self.assertEqual([e.seq for e in store.read_from(6)], [6, 7, 8, 9, 10])
        self.assertEqual(list(store.read_from(11)), [])

    def test_partial_last_line_is_removed(self):
        store = self.open_store()
        store.append([receive(1), receive(2)])
        store.close()
        path = list_segments(self.tmp / "segments")[-1].path
        with path.open("a", encoding="utf-8") as f:
            f.write('{"v":2,"seq":3,"type":"Rece')
        store = self.open_store()
        self.assertEqual(store.last_seq, 2)
        self.assertEqual(store.append([receive(3)])[0].seq, 3)

    def test_removed_segments(self):
        store = self.open_store(max_bytes=300)
        for i in range(10):
            store.append([receive(i + 1)])
        first_of_last = store.segments()[-1].first_seq
        removed = store.remove_segments_upto(first_of_last - 1)
        self.assertTrue(removed)
        self.assertEqual(store.first_seq, first_of_last)
        with self.assertRaises(StoreError):
            list(store.read_from(1))


if __name__ == "__main__":
    unittest.main()
