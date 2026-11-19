"""Command line: imagepolicy CURRENT [--track T] [--prerelease] < tags.txt"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .api import select_tag


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="imagepolicy", description="Select the image tag to roll out.")
    parser.add_argument("current", help="tag that runs now")
    parser.add_argument("--track", default="minor", choices=["patch", "minor", "major"])
    parser.add_argument("--prerelease", action="store_true", help="allow pre-release tags")
    args = parser.parse_args(argv)
    tags = [line.strip() for line in sys.stdin if line.strip()]
    try:
        tag = select_tag(args.current, tags, track=args.track, allow_prerelease=args.prerelease)
    except ValueError as error:
        print(f"imagepolicy: {error}", file=sys.stderr)
        return 2
    if tag is None:
        print(f"imagepolicy: no newer tag for {args.current} on track {args.track}", file=sys.stderr)
        return 1
    print(tag)
    return 0
