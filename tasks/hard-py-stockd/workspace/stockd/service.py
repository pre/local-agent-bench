"""The inventory service: commands in, events out.

execute() validates a command against the projection, writes its events to
the store and then applies them to the projection. All events of one command
are written with one call of EventStore.append().
"""

import logging

from .catalog import Catalog
from .clock import Clock, default_clock
from .commands import Command, parse_command
from .config import Config
from .errors import CommandError
from .events import Draft, draft
from .recovery import RecoveryStats, recover
from .snapshot import SnapshotStore
from .store import EventStore

log = logging.getLogger(__name__)


class InventoryService:
    def __init__(self, config: Config, clock: Clock | None = None):
        self.config = config
        self.catalog = Catalog.load(config.catalog_file)
        self.store = EventStore(config.segments_dir, config.segment_max_bytes, clock or default_clock())
        self.snapshots = SnapshotStore(config.snapshots_dir, config.snapshot_keep)
        self.store.open()
        try:
            self.inventory, self.requests, self.recovery = recover(self.store, self.snapshots,
                                                                   config.request_window)
        except Exception:
            self.store.close()
            raise
        self.store.add_rotate_listener(self._on_rotate)

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "InventoryService":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # Snapshots

    def _on_rotate(self, closed_last_seq: int) -> None:
        # A closed segment is a good point for a snapshot: compaction can then
        # remove the segment.
        self.snapshots.write(self.inventory, closed_last_seq)

    def snapshot(self) -> int:
        """Write a snapshot of the current state. Return its seq."""
        seq = self.store.last_seq
        self.snapshots.write(self.inventory, seq)
        return seq

    # Commands

    def execute(self, obj: object) -> dict:
        rid = obj.get("request_id") if isinstance(obj, dict) else None
        if isinstance(rid, str) and rid in self.requests:
            log.info("request %s: duplicate, not applied again", rid)
            return {"request_id": rid, "status": "duplicate"}
        try:
            command = parse_command(obj, self.config.max_receive_lines)
            drafts, extra = self._plan(command)
        except CommandError as e:
            log.info("request %s: rejected: %s", rid, e)
            return {"request_id": rid if isinstance(rid, str) else None, "status": "rejected", "error": str(e)}
        if not drafts:
            return {"request_id": rid, "status": "ignored", **extra}
        events = self.store.append(drafts)
        for event in events:
            self.inventory.apply(event)
        if rid is not None:
            self.requests.add(rid)
        return {"request_id": rid, "status": "applied", "seq": events[-1].seq, **extra}

    def _plan(self, command: Command) -> tuple[list[Draft], dict]:
        a, rid, inv = command.args, command.request_id, self.inventory
        if command.op == "receive":
            drafts = []
            for line in a["lines"]:
                qty = line.qty if line.qty is not None else self.catalog.units(line.sku, line.packs)
                drafts.append(draft("Received", rid, warehouse=a["warehouse"], sku=line.sku, qty=qty))
            return drafts, {}
        if command.op == "adjust":
            level = inv.peek(a["warehouse"], a["sku"])
            if level.on_hand + a["delta"] < level.reserved:
                raise CommandError("adjustment would leave less stock than reserved")
            return [draft("Adjusted", rid, **a)], {}
        if command.op == "reserve":
            if inv.peek(a["warehouse"], a["sku"]).available < a["qty"]:
                raise CommandError("insufficient stock")
            number = inv.next_reservation
            return [draft("Reserved", rid, reservation=number, **a)], {"reservation": number}
        if command.op == "release":
            if a["reservation"] not in inv.reservations:
                log.info("release: unknown reservation %s, ignored", a["reservation"])
                return [], {}
            return [draft("Released", rid, reservation=a["reservation"])], {}
        if command.op == "ship":
            if a["reservation"] not in inv.reservations:
                raise CommandError(f"unknown reservation {a['reservation']}")
            return [draft("Shipped", rid, reservation=a["reservation"])], {}
        # transfer: two events, out of one warehouse and into the other
        if inv.peek(a["from"], a["sku"]).available < a["qty"]:
            raise CommandError("insufficient stock")
        number = inv.next_transfer
        return [draft("TransferredOut", rid, transfer=number, warehouse=a["from"], sku=a["sku"], qty=a["qty"]),
                draft("TransferredIn", rid, transfer=number, warehouse=a["to"], sku=a["sku"], qty=a["qty"])], \
            {"transfer": number}

    @property
    def recovery_stats(self) -> RecoveryStats:
        return self.recovery
