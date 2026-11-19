"""Recovery: build the projection and the request log from the data directory."""

import logging
from dataclasses import dataclass

from .errors import RecoveryError, StoreError
from .idempotency import RequestLog
from .projection import Inventory
from .snapshot import SnapshotStore
from .store import EventStore

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecoveryStats:
    snapshot_seq: int | None
    replayed: int
    last_seq: int


def recover(store: EventStore, snapshots: SnapshotStore | None, request_window: int
            ) -> tuple[Inventory, RequestLog, RecoveryStats]:
    """Load the newest snapshot (if snapshots is not None) and replay the events after it."""
    inventory = Inventory()
    requests = RequestLog(request_window)
    start = 1
    snapshot = snapshots.latest() if snapshots is not None else None
    if snapshot is not None:
        inventory = Inventory.from_dict(snapshot.state)
        inventory.applied_seq = snapshot.seq
        start = snapshot.seq + 1
    if start < store.first_seq:
        raise RecoveryError(f"the log starts at seq {store.first_seq}, but recovery needs seq {start}"
                            " (were segments removed without a snapshot?)")
    replayed = 0
    try:
        for event in store.read_from(start):
            inventory.apply(event)
            if event.rid is not None:
                requests.add(event.rid)
            replayed += 1
    except StoreError as e:
        raise RecoveryError(str(e)) from None
    stats = RecoveryStats(snapshot.seq if snapshot else None, replayed, store.last_seq)
    log.info("recovered: snapshot seq %s, replayed %d events, last seq %d",
             stats.snapshot_seq if stats.snapshot_seq is not None else "none", replayed, store.last_seq)
    return inventory, requests, stats
