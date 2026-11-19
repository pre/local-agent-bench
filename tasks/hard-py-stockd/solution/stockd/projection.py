"""The projection: the current stock, built from the events.

apply() is the only way to change the projection. It must give the same state
for the same events, in a live service and in a replay.
"""

import logging
from dataclasses import asdict, dataclass

from .events import Event

log = logging.getLogger(__name__)


@dataclass
class Level:
    on_hand: int = 0
    reserved: int = 0

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


@dataclass(frozen=True)
class Reservation:
    warehouse: str
    sku: str
    qty: int
    order: str


class Inventory:
    def __init__(self) -> None:
        self.levels: dict[str, dict[str, Level]] = {}
        self.reservations: dict[int, Reservation] = {}
        self.next_reservation = 1
        self.next_transfer = 1
        # The sequence number of the last event that apply() processed.
        self.applied_seq = 0

    # Queries

    def peek(self, warehouse: str, sku: str) -> Level:
        """The level of a SKU in a warehouse. Does not add a row."""
        return self.levels.get(warehouse, {}).get(sku, Level())

    def _level(self, warehouse: str, sku: str) -> Level:
        return self.levels.setdefault(warehouse, {}).setdefault(sku, Level())

    def rows(self) -> list[tuple[str, str, Level]]:
        return [(wh, sku, self.levels[wh][sku]) for wh in sorted(self.levels) for sku in sorted(self.levels[wh])]

    # Events

    def apply(self, event: Event) -> None:
        handler = getattr(self, "_on_" + event.type)
        handler(**event.data)
        self.applied_seq = event.seq

    def _on_Received(self, warehouse: str, sku: str, qty: int) -> None:
        self._level(warehouse, sku).on_hand += qty

    def _on_Adjusted(self, warehouse: str, sku: str, delta: int, reason: str) -> None:
        self._level(warehouse, sku).on_hand += delta

    def _on_Reserved(self, reservation: int, warehouse: str, sku: str, qty: int, order: str) -> None:
        self.reservations[reservation] = Reservation(warehouse, sku, qty, order)
        self._level(warehouse, sku).reserved += qty
        self.next_reservation = max(self.next_reservation, reservation + 1)

    def _on_Released(self, reservation: int) -> None:
        res = self.reservations.pop(reservation, None)
        if res is None:
            log.warning("release of unknown reservation %s ignored", reservation)
            return
        self._level(res.warehouse, res.sku).reserved -= res.qty

    def _on_Shipped(self, reservation: int) -> None:
        res = self.reservations.pop(reservation, None)
        if res is None:
            log.warning("shipment of unknown reservation %s ignored", reservation)
            return
        level = self._level(res.warehouse, res.sku)
        level.reserved -= res.qty
        level.on_hand -= res.qty

    def _on_TransferredOut(self, transfer: int, warehouse: str, sku: str, qty: int) -> None:
        self._level(warehouse, sku).on_hand -= qty
        self.next_transfer = max(self.next_transfer, transfer + 1)

    def _on_TransferredIn(self, transfer: int, warehouse: str, sku: str, qty: int) -> None:
        self._level(warehouse, sku).on_hand += qty
        self.next_transfer = max(self.next_transfer, transfer + 1)

    # Snapshots

    def to_dict(self) -> dict:
        return {
            "levels": {wh: {sku: [lv.on_hand, lv.reserved] for sku, lv in skus.items()}
                       for wh, skus in self.levels.items()},
            "reservations": {rid: asdict(res) for rid, res in self.reservations.items()},
            "next_reservation": self.next_reservation,
            "next_transfer": self.next_transfer,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Inventory":
        inv = cls()
        inv.levels = {wh: {sku: Level(*pair) for sku, pair in skus.items()}
                      for wh, skus in data["levels"].items()}
        # JSON object keys are strings: convert the reservation numbers back to int.
        inv.reservations = {int(rid): Reservation(**res) for rid, res in data["reservations"].items()}
        inv.next_reservation = data["next_reservation"]
        inv.next_transfer = data["next_transfer"]
        return inv
