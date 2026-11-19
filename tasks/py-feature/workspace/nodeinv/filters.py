"""Select nodes by role, zone and labels."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .inventory import Node


def parse_label_selector(items: Sequence[str]) -> dict[str, str]:
    """Convert ["pool=gpu", "tier=prod"] to {"pool": "gpu", "tier": "prod"}."""
    selector = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise ValueError(f"label selector {item!r}: use KEY=VALUE")
        selector[key] = value
    return selector


def select_nodes(
    nodes: Iterable[Node],
    role: str | None = None,
    zone: str | None = None,
    labels: dict[str, str] | None = None,
    include_cordoned: bool = False,
) -> list[Node]:
    """Return the nodes that match all given conditions, in input order."""
    labels = labels or {}
    selected = []
    for node in nodes:
        if node.cordoned and not include_cordoned:
            continue
        if role is not None and node.role != role:
            continue
        if zone is not None and node.zone != zone:
            continue
        if any(node.labels.get(key) != value for key, value in labels.items()):
            continue
        selected.append(node)
    return selected
