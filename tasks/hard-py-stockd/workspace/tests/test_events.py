import json
import unittest

from stockd.events import FORMAT_VERSION, decode, draft, encode


class EventCodecTest(unittest.TestCase):
    def test_round_trip(self):
        event = draft("Received", "rcv-1", warehouse="WH-1", sku="BOLT-M8", qty=50).at(7, "2026-11-16T08:00:00Z")
        line = encode(event)
        self.assertTrue(line.endswith("\n"))
        self.assertEqual(decode(line), event)
        self.assertEqual(json.loads(line)["v"], FORMAT_VERSION)

    def test_no_rid_is_not_written(self):
        event = draft("Released", reservation=3).at(1, "2026-11-16T08:00:00Z")
        self.assertNotIn("rid", json.loads(encode(event)))
        self.assertIsNone(decode(encode(event)).rid)

    def test_draft_checks_fields(self):
        with self.assertRaises(ValueError):
            draft("Received", warehouse="WH-1", sku="A")
        with self.assertRaises(ValueError):
            draft("Exploded", warehouse="WH-1")

    def test_non_ascii_text(self):
        event = draft("Adjusted", warehouse="WH-1", sku="A", delta=-2, reason="Bruch beim Umräumen").at(
            2, "2026-11-16T08:00:00Z")
        self.assertEqual(decode(encode(event)).data["reason"], "Bruch beim Umräumen")


class UpcastTest(unittest.TestCase):
    def test_version_1_receive(self):
        event = decode('{"seq":3,"type":"receive","ts":"2026-02-01T10:00:00Z","data":{"wh":"WH-1","sku":"A","n":4}}')
        self.assertEqual(event.type, "Received")
        self.assertEqual(event.data, {"warehouse": "WH-1", "sku": "A", "qty": 4})

    def test_version_1_adjust_without_reason(self):
        event = decode('{"seq":4,"type":"adjust","ts":"2026-02-01T10:00:00Z","data":{"wh":"WH-1","sku":"A","d":-1}}')
        self.assertEqual(event.data, {"warehouse": "WH-1", "sku": "A", "delta": -1, "reason": ""})

    def test_version_1_reserve(self):
        event = decode('{"seq":5,"type":"reserve","ts":"t","rid":"x",'
                       '"data":{"res":9,"wh":"WH-2","sku":"B","n":2,"ord":"SO-1"}}')
        self.assertEqual(event.data, {"reservation": 9, "warehouse": "WH-2", "sku": "B", "qty": 2, "order": "SO-1"})
        self.assertEqual(event.rid, "x")

    def test_unknown_version(self):
        with self.assertRaises(ValueError):
            decode('{"v":3,"seq":1,"type":"Received","ts":"t","data":{}}')


if __name__ == "__main__":
    unittest.main()
