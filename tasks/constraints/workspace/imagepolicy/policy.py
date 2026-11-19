"""Update tracks: which versions a cluster may move to."""

from __future__ import annotations

from enum import Enum

from .versions import Version


class Track(str, Enum):
    PATCH = "patch"  # same major and minor version
    MINOR = "minor"  # same major version
    MAJOR = "major"  # any newer version

    @classmethod
    def parse(cls, value: str) -> "Track":
        try:
            return cls(value)
        except ValueError:
            names = ", ".join(t.value for t in cls)
            raise ValueError(f"unknown track {value!r}, use one of: {names}") from None


def allowed(current: Version, candidate: Version, track: Track) -> bool:
    """True if the track allows a move from current to candidate.

    The caller checks that the candidate is newer.
    """
    if track is Track.PATCH:
        return candidate.core[:2] == current.core[:2]
    if track is Track.MINOR:
        return candidate.major == current.major
    return True
