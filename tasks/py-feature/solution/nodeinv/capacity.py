"""Sum the capacity of nodes, grouped by an attribute."""

from __future__ import annotations

from collections.abc import Iterable

from .inventory import Node

GROUP_ATTRIBUTES = ("rack", "zone", "role")
NO_VALUE = "-"


def _totals(nodes: list[Node]) -> dict[str, int]:
    return {
        "nodes": len(nodes),
        "cpu": sum(node.cpu for node in nodes),
        "mem_gib": sum(node.memory_mib for node in nodes) // 1024,
        "gpu": sum(node.gpu_count for node in nodes),
    }


def summarize_capacity(nodes: Iterable[Node], by: str) -> list[dict]:
    """Return one dict for each group, sorted by group name."""
    if by not in GROUP_ATTRIBUTES:
        raise ValueError(f"cannot group by {by!r}")
    groups: dict[str, list[Node]] = {}
    for node in nodes:
        groups.setdefault(node.attribute(by) or NO_VALUE, []).append(node)
    return [{"name": name, **_totals(members)} for name, members in sorted(groups.items())]


def total_capacity(nodes: Iterable[Node]) -> dict[str, int]:
    return _totals(list(nodes))
