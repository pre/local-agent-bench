"""Events: the records of the event log.

A line of a segment file is one event as a JSON object:

    {"data": {...}, "rid": "rcv-881", "seq": 412, "ts": "2026-11-17T02:10:04Z", "type": "Received", "v": 2}

Lines without "v" come from version 1 of stockd (before 2026-03). They used
short field names and lower case types. decode() converts them to version 2.
"""

import json
from dataclasses import dataclass, field

FORMAT_VERSION = 2

# The data fields of each event type, in a fixed order.
EVENT_FIELDS: dict[str, tuple[str, ...]] = {
    "Received": ("warehouse", "sku", "qty"),
    "Adjusted": ("warehouse", "sku", "delta", "reason"),
    "Reserved": ("reservation", "warehouse", "sku", "qty", "order"),
    "Released": ("reservation",),
    "Shipped": ("reservation",),
    "TransferredOut": ("transfer", "warehouse", "sku", "qty"),
    "TransferredIn": ("transfer", "warehouse", "sku", "qty"),
}

_V1_TYPES = {
    "receive": "Received",
    "adjust": "Adjusted",
    "reserve": "Reserved",
    "release": "Released",
    "ship": "Shipped",
}
_V1_FIELDS = {"wh": "warehouse", "n": "qty", "d": "delta", "res": "reservation", "ord": "order"}


@dataclass(frozen=True)
class Draft:
    """An event before the store gives it a sequence number and a time."""

    type: str
    data: dict = field(default_factory=dict)
    rid: str | None = None

    def at(self, seq: int, ts: str) -> "Event":
        return Event(seq=seq, type=self.type, data=self.data, ts=ts, rid=self.rid)


@dataclass(frozen=True)
class Event:
    seq: int
    type: str
    data: dict
    ts: str
    rid: str | None = None


def draft(type_: str, rid: str | None = None, **data) -> Draft:
    expected = EVENT_FIELDS.get(type_)
    if expected is None:
        raise ValueError(f"unknown event type {type_!r}")
    if set(data) != set(expected):
        raise ValueError(f"{type_} needs the fields {', '.join(expected)}, not {', '.join(sorted(data))}")
    return Draft(type=type_, data={name: data[name] for name in expected}, rid=rid)


def encode(event: Event) -> str:
    obj = {"v": FORMAT_VERSION, "seq": event.seq, "type": event.type, "ts": event.ts, "data": event.data}
    if event.rid is not None:
        obj["rid"] = event.rid
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def decode(line: str) -> Event:
    obj = json.loads(line)
    if not isinstance(obj, dict):
        raise ValueError("an event must be a JSON object")
    if "v" not in obj:
        obj = upcast_v1(obj)
    elif obj["v"] != FORMAT_VERSION:
        raise ValueError(f"unknown event format version {obj['v']!r}")
    type_ = obj["type"]
    if type_ not in EVENT_FIELDS:
        raise ValueError(f"unknown event type {type_!r}")
    return Event(seq=obj["seq"], type=type_, data=obj["data"], ts=obj["ts"], rid=obj.get("rid"))


def upcast_v1(obj: dict) -> dict:
    """Convert an event of format version 1 to version 2."""
    type_ = _V1_TYPES.get(obj.get("type"))
    if type_ is None:
        raise ValueError(f"unknown version 1 event type {obj.get('type')!r}")
    data = {_V1_FIELDS.get(k, k): v for k, v in obj.get("data", {}).items()}
    if type_ == "Adjusted":
        data.setdefault("reason", "")
    return {"v": FORMAT_VERSION, "seq": obj["seq"], "type": type_, "ts": obj.get("ts", ""),
            "data": data, "rid": obj.get("rid")}
