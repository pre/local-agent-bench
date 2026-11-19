"""Data classes of the jobq client."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from .durations import parse_duration


def parse_time(text):
    """Parse an RFC 3339 time of the server, for example 2026-11-19T10:00:00.123456789Z."""
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Go writes up to 9 fraction digits, Python accepts at most 6.
    head, sep, rest = text.partition(".")
    if sep:
        digits = ""
        i = 0
        while i < len(rest) and rest[i].isdigit():
            digits += rest[i]
            i += 1
        text = f"{head}.{digits[:6].ljust(6, '0')}{rest[i:]}"
    return datetime.fromisoformat(text)


@dataclass(frozen=True)
class Job:
    id: str
    command: list
    timeout: timedelta
    state: str
    created_at: datetime

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=str(data["id"]),
            command=list(data["command"]),
            timeout=parse_duration(data["timeout"]),
            state=data["state"],
            created_at=parse_time(data["created_at"]),
        )
