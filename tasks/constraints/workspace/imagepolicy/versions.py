"""Parse and order image tags that carry a semantic version."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TAG = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: str = ""
    build: str = ""
    tag: str = ""

    @property
    def is_prerelease(self) -> bool:
        return self.prerelease != ""

    @property
    def core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)


def parse(tag: str) -> Version | None:
    """Return the version of a tag, or None if the tag is not a version.

    Accepts an optional "v" prefix, for example "v1.4.0" and "1.4.0-rc.2".
    """
    match = _TAG.match(tag.strip())
    if not match:
        return None
    return Version(
        major=int(match["major"]),
        minor=int(match["minor"]),
        patch=int(match["patch"]),
        prerelease=match["pre"] or "",
        build=match["build"] or "",
        tag=tag,
    )


def sort_key(version: Version) -> tuple:
    """Key for sorted() and max(): orders versions by precedence.

    Build metadata does not change the precedence.
    """
    return (version.major, version.minor, version.patch, version.prerelease)


def compare(a: str, b: str) -> int:
    """Compare two tags: -1 if a < b, 0 if equal precedence, 1 if a > b.

    Raises ValueError if a tag is not a version.
    """
    va, vb = parse(a), parse(b)
    if va is None or vb is None:
        raise ValueError(f"not a version: {a if va is None else b!r}")
    ka, kb = sort_key(va), sort_key(vb)
    return (ka > kb) - (ka < kb)
