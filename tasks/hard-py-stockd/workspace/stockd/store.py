"""The event store: append-only, split into segment files."""

import logging
from pathlib import Path
from typing import Callable, Iterator

from .clock import Clock
from .errors import StoreError
from .events import Draft, Event, encode
from .segments import Segment, last_event, list_segments, read_events, repair_tail, segment_name

log = logging.getLogger(__name__)

RotateListener = Callable[[int], None]


class EventStore:
    def __init__(self, directory: Path, max_bytes: int, clock: Clock):
        self.directory = directory
        self.max_bytes = max_bytes
        self.clock = clock
        self.last_seq = 0
        self._segments: list[Segment] = []
        self._active = None
        self._active_size = 0
        self._listeners: list[RotateListener] = []

    # Opening and closing

    def open(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._segments = list_segments(self.directory)
        if not self._segments:
            self._segments = [Segment(1, self.directory / segment_name(1))]
            self._segments[0].path.touch()
            self.last_seq = 0
        else:
            tail = self._segments[-1]
            repair_tail(tail.path)
            event = last_event(tail.path)
            self.last_seq = event.seq if event else tail.first_seq - 1
        active = self._segments[-1].path
        self._active = active.open("a", encoding="utf-8")
        self._active_size = active.stat().st_size
        log.debug("opened %d segments, last seq %d", len(self._segments), self.last_seq)

    def close(self) -> None:
        if self._active is not None:
            self._active.close()
            self._active = None

    def __enter__(self) -> "EventStore":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # Segments

    @property
    def first_seq(self) -> int:
        return self._segments[0].first_seq

    def segments(self) -> list[Segment]:
        return list(self._segments)

    def add_rotate_listener(self, listener: RotateListener) -> None:
        """Call listener(last_seq_of_closed_segment) each time a segment is closed."""
        self._listeners.append(listener)

    def _rotate(self) -> None:
        closed_last = self.last_seq
        self._active.close()
        segment = Segment(closed_last + 1, self.directory / segment_name(closed_last + 1))
        segment.path.touch()
        self._segments.append(segment)
        self._active = segment.path.open("a", encoding="utf-8")
        self._active_size = 0
        log.info("segment %s closed at seq %d, new segment %s", segment_name(self._segments[-2].first_seq),
                 closed_last, segment.path.name)
        for listener in self._listeners:
            listener(closed_last)

    # Writing and reading

    def append(self, drafts: list[Draft]) -> list[Event]:
        """Write the events of one command. Return them with their sequence numbers."""
        if self._active is None:
            raise StoreError("the store is not open")
        written = []
        for d in drafts:
            if self._active_size >= self.max_bytes:
                self._rotate()
            event = d.at(self.last_seq + 1, self.clock.now())
            line = encode(event)
            self._active.write(line)
            self._active.flush()
            self._active_size += len(line.encode("utf-8"))
            self.last_seq = event.seq
            written.append(event)
        return written

    def read_from(self, seq: int) -> Iterator[Event]:
        """Yield the events with a sequence number of seq or more, in order."""
        if seq < self.first_seq:
            raise StoreError(f"event {seq} is not in the log any more (first seq {self.first_seq})")
        expected = seq
        for i, segment in enumerate(self._segments):
            nxt = self._segments[i + 1].first_seq if i + 1 < len(self._segments) else None
            if nxt is not None and nxt <= seq:
                continue
            for event in read_events(segment.path):
                if event.seq < seq:
                    continue
                if event.seq != expected:
                    raise StoreError(f"{segment.path.name}: expected seq {expected}, found {event.seq}")
                expected += 1
                yield event

    def remove_segments_upto(self, seq: int) -> list[Path]:
        """Remove the closed segments that contain only events up to seq. Return the removed paths."""
        removed = []
        while len(self._segments) > 1 and self._segments[1].first_seq - 1 <= seq:
            segment = self._segments.pop(0)
            segment.path.unlink()
            removed.append(segment.path)
        return removed
