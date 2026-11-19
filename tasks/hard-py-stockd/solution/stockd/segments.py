"""Segment files of the event log.

The event log is a sequence of segment files in <data>/segments. The name of a
segment is the sequence number of its first event, with 12 digits, and the
suffix ".seg", for example 000000000413.seg. Each line is one event. The
sequence numbers are continuous over all segments.
"""

import codecs
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .errors import StoreError
from .events import Event, decode

log = logging.getLogger(__name__)

SUFFIX = ".seg"


@dataclass(frozen=True)
class Segment:
    first_seq: int
    path: Path


def segment_name(first_seq: int) -> str:
    return f"{first_seq:012d}{SUFFIX}"


def list_segments(directory: Path) -> list[Segment]:
    segments = []
    for path in directory.iterdir():
        if path.suffix != SUFFIX:
            continue
        stem = path.name[: -len(SUFFIX)]
        if len(stem) != 12 or not stem.isdigit():
            log.warning("ignoring %s: not a segment name", path.name)
            continue
        segments.append(Segment(int(stem), path))
    segments.sort(key=lambda s: s.first_seq)
    return segments


# Segments of a busy day are large. Recovery reads them in blocks and splits
# the lines itself, which is faster than the line iteration of a text file.
READ_BLOCK = 8192


def _lines(path: Path) -> Iterator[str]:
    with path.open("rb") as f:
        pending = ""
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            block = f.read(READ_BLOCK)
            if not block:
                break
            # A damaged byte must not stop the recovery: it becomes U+FFFD.
            # The incremental decoder keeps a character that a block boundary
            # splits until the next block.
            text = pending + decoder.decode(block)
            lines = text.split("\n")
            pending = lines.pop()
            yield from lines
        pending += decoder.decode(b"", final=True)
        if pending:
            yield pending


def read_events(path: Path) -> Iterator[Event]:
    for number, line in enumerate(_lines(path), start=1):
        if not line.strip():
            continue
        try:
            yield decode(line)
        except (ValueError, KeyError) as e:
            raise StoreError(f"{path.name} line {number}: {e}") from None


def last_event(path: Path) -> Event | None:
    event = None
    for event in read_events(path):
        pass
    return event


def repair_tail(path: Path) -> int:
    """Remove a partial last line (a write that a crash stopped). Return the bytes removed."""
    size = path.stat().st_size
    if size == 0:
        return 0
    with path.open("rb+") as f:
        f.seek(-1, os.SEEK_END)
        if f.read(1) == b"\n":
            return 0
        f.seek(0)
        content = f.read()
        keep = content.rfind(b"\n") + 1
        f.truncate(keep)
    removed = size - keep
    log.warning("%s: removed a partial last line of %d bytes", path.name, removed)
    return removed
