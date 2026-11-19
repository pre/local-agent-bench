"""Command line interface of nodeinv."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence

from . import __version__
from .filters import parse_label_selector, select_nodes
from .inventory import Inventory, InventoryError, Node, load_inventory
from .render import human_mib, table

DEFAULT_INVENTORY = "inventory.toml"


def _add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--role", help="only nodes with this role")
    parser.add_argument("--zone", help="only nodes in this zone")
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="only nodes with this label (repeat for more labels)",
    )
    parser.add_argument(
        "--include-cordoned",
        action="store_true",
        help="also show nodes that are cordoned",
    )


def _selected(inventory: Inventory, args: argparse.Namespace) -> list[Node]:
    return select_nodes(
        inventory.nodes,
        role=args.role,
        zone=args.zone,
        labels=parse_label_selector(args.label),
        include_cordoned=args.include_cordoned,
    )


def _node_dict(node: Node) -> dict:
    return {
        "name": node.name,
        "role": node.role,
        "zone": node.zone,
        "rack": node.rack,
        "cpu": node.cpu,
        "memory_mib": node.memory_mib,
        "gpu_model": node.gpu_model,
        "gpu_count": node.gpu_count,
        "labels": node.labels,
        "cordoned": node.cordoned,
    }


def cmd_list(inventory: Inventory, args: argparse.Namespace) -> int:
    nodes = _selected(inventory, args)
    if args.json:
        print(json.dumps([_node_dict(node) for node in nodes], indent=2))
        return 0
    rows = [
        (
            node.name,
            node.role,
            node.zone,
            node.rack,
            node.cpu,
            human_mib(node.memory_mib),
            node.gpu_count,
            "cordoned" if node.cordoned else "ready",
        )
        for node in nodes
    ]
    print(table(("NAME", "ROLE", "ZONE", "RACK", "CPU", "MEMORY", "GPU", "STATUS"), rows))
    return 0


def cmd_show(inventory: Inventory, args: argparse.Namespace) -> int:
    node = inventory.find(args.name)
    if node is None:
        print(f"nodeinv: no node named {args.name!r}", file=sys.stderr)
        return 1
    print(json.dumps(_node_dict(node), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nodeinv", description="Query the node inventory of a cluster.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--inventory",
        default=os.environ.get("NODEINV_INVENTORY", DEFAULT_INVENTORY),
        help=f"inventory file (default: $NODEINV_INVENTORY or {DEFAULT_INVENTORY})",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    list_parser = commands.add_parser("list", help="list nodes")
    _add_filter_arguments(list_parser)
    list_parser.add_argument("--json", action="store_true", help="print JSON")
    list_parser.set_defaults(handler=cmd_list)

    show_parser = commands.add_parser("show", help="show one node")
    show_parser.add_argument("name")
    show_parser.set_defaults(handler=cmd_show)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        inventory = load_inventory(args.inventory)
        return args.handler(inventory, args)
    except FileNotFoundError:
        print(f"nodeinv: inventory file {args.inventory} not found", file=sys.stderr)
        return 1
    except (InventoryError, ValueError) as error:
        print(f"nodeinv: {error}", file=sys.stderr)
        return 1
