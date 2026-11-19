"""Print the plan of the nodes in a CSV file (columns: site,rack,slot,role)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Sequence

from .plan import Node, node_plan


def read_nodes(path: str) -> list[Node]:
    with open(path, newline="") as handle:
        return [
            Node(site=row["site"], rack=int(row["rack"]), slot=int(row["slot"]), role=row["role"])
            for row in csv.DictReader(handle)
        ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="addrplan", description=__doc__)
    parser.add_argument("csv", help="node list")
    args = parser.parse_args(argv)
    try:
        plans = [node_plan(node) for node in read_nodes(args.csv)]
    except (OSError, ValueError, KeyError) as error:
        print(f"addrplan: {error}", file=sys.stderr)
        return 1
    print(json.dumps(plans, indent=2))
    return 0
