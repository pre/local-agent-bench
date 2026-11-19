"""Load the node inventory of a cluster from a TOML file."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_UNITS_MIB = {"Mi": 1, "Gi": 1024, "Ti": 1024 * 1024}
_QUANTITY = re.compile(r"^(\d+(?:\.\d+)?)(Mi|Gi|Ti)$")


class InventoryError(ValueError):
    """The inventory file is not valid."""


@dataclass(frozen=True)
class Node:
    name: str
    role: str
    zone: str
    rack: str | None
    cpu: int
    memory_mib: int
    gpu_model: str | None = None
    gpu_count: int = 0
    labels: dict[str, str] = field(default_factory=dict)
    cordoned: bool = False

    def attribute(self, name: str) -> str | None:
        """Return the value of a grouping attribute: role, zone or rack."""
        if name not in ("role", "zone", "rack"):
            raise KeyError(name)
        return getattr(self, name)


@dataclass(frozen=True)
class Inventory:
    cluster: str
    nodes: list[Node]

    def find(self, name: str) -> Node | None:
        for node in self.nodes:
            if node.name == name:
                return node
        return None


def parse_memory(value: str) -> int:
    """Convert a Kubernetes-style quantity such as "512Gi" to MiB."""
    match = _QUANTITY.match(value.strip())
    if not match:
        raise InventoryError(f"memory {value!r}: use a number with Mi, Gi or Ti")
    number, unit = match.groups()
    return int(float(number) * _UNITS_MIB[unit])


def _node_from_table(entry: dict) -> Node:
    try:
        name = entry["name"]
        role = entry["role"]
        zone = entry["zone"]
        cpu = int(entry["cpu"])
        memory_mib = parse_memory(entry["memory"])
    except KeyError as missing:
        raise InventoryError(f"node {entry.get('name', '?')}: missing key {missing}") from None
    gpu = entry.get("gpu") or {}
    return Node(
        name=name,
        role=role,
        zone=zone,
        rack=entry.get("rack"),
        cpu=cpu,
        memory_mib=memory_mib,
        gpu_model=gpu.get("model"),
        gpu_count=int(gpu.get("count", 0)),
        labels={str(k): str(v) for k, v in entry.get("labels", {}).items()},
        cordoned=bool(entry.get("cordoned", False)),
    )


def load_inventory(path: str | Path) -> Inventory:
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    cluster = data.get("cluster", {}).get("name", "unknown")
    nodes = [_node_from_table(entry) for entry in data.get("nodes", [])]
    names = [node.name for node in nodes]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise InventoryError(f"duplicate node names: {', '.join(duplicates)}")
    return Inventory(cluster=cluster, nodes=nodes)
