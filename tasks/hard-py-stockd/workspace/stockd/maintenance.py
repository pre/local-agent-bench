"""Maintenance commands: compaction and the check of the event log."""

import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .errors import StoreError
from .segments import read_events
from .snapshot import SnapshotStore
from .store import EventStore

log = logging.getLogger(__name__)


def compact(store: EventStore, snapshots: SnapshotStore) -> list[Path]:
    """Remove the segments that the newest snapshot contains completely."""
    snapshot = snapshots.latest()
    if snapshot is None:
        log.info("compact: no snapshot, nothing to remove")
        return []
    removed = store.remove_segments_upto(snapshot.seq)
    for path in removed:
        log.info("compact: removed %s (snapshot seq %d)", path.name, snapshot.seq)
    return removed


@dataclass
class LogCheck:
    segments: int = 0
    events: int = 0
    first_seq: int | None = None
    last_seq: int | None = None
    by_type: Counter = field(default_factory=Counter)
    v1_events: int = 0
    problems: list[str] = field(default_factory=list)


def check_log(store: EventStore) -> LogCheck:
    """Read all segments and report gaps and damaged lines. Changes nothing."""
    result = LogCheck()
    expected = None
    for segment in store.segments():
        result.segments += 1
        try:
            raw_lines = segment.path.read_text(encoding="utf-8").splitlines()
            result.v1_events += sum(1 for line in raw_lines if line.strip() and '"v":' not in line)
            first_in_segment = True
            for event in read_events(segment.path):
                if expected is not None and event.seq != expected:
                    result.problems.append(f"{segment.path.name}: expected seq {expected}, found {event.seq}")
                if first_in_segment and event.seq != segment.first_seq:
                    result.problems.append(f"{segment.path.name}: first event has seq {event.seq}")
                first_in_segment = False
                if result.first_seq is None:
                    result.first_seq = event.seq
                result.last_seq = event.seq
                result.events += 1
                result.by_type[event.type] += 1
                expected = event.seq + 1
        except StoreError as e:
            result.problems.append(str(e))
    return result
