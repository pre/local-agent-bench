"""Snapshots of the projection.

A snapshot file is <data>/snapshots/snap-<seq>.json, where <seq> (12 digits)
is the sequence number of the last event that the snapshot contains:

    {"format": 1, "seq": 412, "state": {...Inventory.to_dict()...}}

Recovery loads the newest snapshot that it can read and replays the events
after its seq. A snapshot is written to a temporary file first and then
renamed, so a crash never leaves a partial snapshot with the final name.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .projection import Inventory

log = logging.getLogger(__name__)

SNAPSHOT_FORMAT = 1
_PREFIX = "snap-"
_SUFFIX = ".json"


@dataclass(frozen=True)
class Snapshot:
    seq: int
    state: dict
    path: Path


class SnapshotStore:
    def __init__(self, directory: Path, keep: int):
        self.directory = directory
        self.keep = keep

    def _path(self, seq: int) -> Path:
        return self.directory / f"{_PREFIX}{seq:012d}{_SUFFIX}"

    def list(self) -> list[tuple[int, Path]]:
        """The snapshot files from the oldest to the newest."""
        if not self.directory.exists():
            return []
        found = []
        for path in self.directory.iterdir():
            name = path.name
            if not (name.startswith(_PREFIX) and name.endswith(_SUFFIX)):
                continue
            digits = name[len(_PREFIX): -len(_SUFFIX)]
            if digits.isdigit():
                found.append((int(digits), path))
        return sorted(found)

    def write(self, inventory: Inventory, seq: int) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(seq)
        tmp = path.with_suffix(".tmp")
        body = {"format": SNAPSHOT_FORMAT, "seq": seq, "state": inventory.to_dict()}
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(body, f, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        log.info("snapshot %s written", path.name)
        self.prune()
        return path

    def prune(self) -> None:
        snapshots = self.list()
        for _, path in snapshots[: max(0, len(snapshots) - self.keep)]:
            path.unlink()
            log.debug("snapshot %s removed", path.name)

    def latest(self) -> Snapshot | None:
        """The newest snapshot that can be read, or None."""
        for seq, path in reversed(self.list()):
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                log.warning("snapshot %s cannot be read, trying an older one: %s", path.name, e)
                continue
            if body.get("format") != SNAPSHOT_FORMAT or body.get("seq") != seq:
                log.warning("snapshot %s has a bad header, trying an older one", path.name)
                continue
            return Snapshot(seq=seq, state=body["state"], path=path)
        return None
