"""Public API of imagepolicy.

The rollout controller and other teams import these functions. Changes to
this file need a review by the owners of the rollout controller.
"""

from __future__ import annotations

from collections.abc import Iterable

from .policy import Track, allowed
from .versions import Version, parse, sort_key


def _versions(tags: Iterable[str]) -> list[Version]:
    return [v for v in (parse(tag) for tag in tags) if v is not None]


def newer_tags(current: str, candidates: Iterable[str]) -> list[str]:
    """Return the candidate tags that are newer than current, oldest first.

    Tags that are not versions are ignored.
    """
    now = parse(current)
    if now is None:
        raise ValueError(f"current tag {current!r} is not a version")
    newer = [v for v in _versions(candidates) if sort_key(v) > sort_key(now)]
    return [v.tag for v in sorted(newer, key=sort_key)]


def select_tag(
    current: str,
    candidates: Iterable[str],
    track: str = "minor",
    allow_prerelease: bool = False,
) -> str | None:
    """Return the tag to roll out, or None if no candidate is allowed.

    The result is the newest candidate that is newer than current and that the
    track allows. Pre-release tags are only candidates with allow_prerelease.
    """
    now = parse(current)
    if now is None:
        raise ValueError(f"current tag {current!r} is not a version")
    policy = Track.parse(track)
    options = [
        v
        for v in _versions(candidates)
        if sort_key(v) > sort_key(now)
        and allowed(now, v, policy)
        and (allow_prerelease or not v.is_prerelease)
    ]
    if not options:
        return None
    return max(options, key=sort_key).tag
