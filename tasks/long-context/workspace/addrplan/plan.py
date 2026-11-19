"""Names, addresses, VLANs and MTUs of a node from its rack position.

The rules come from the network and node addressing standard in
docs/network-standard.md. The rule numbers in the docstrings refer to it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .sites import check_position, get_site

ROLE_CODES = {
    "control-plane": "cp",
    "compute": "cpu",
    "gpu": "gpu",
    "storage": "sto",
    "infra": "inf",
}

NETWORKS = ("bmc", "mgmt", "data", "storage")


@dataclass(frozen=True)
class Node:
    site: str
    rack: int
    slot: int
    role: str


def hostname(site: str, rack: int, slot: int, role: str) -> str:
    """Host name of a node (R-4.2): <site>-<role code>-r<rack>-s<slot>."""
    s = get_site(site)
    check_position(s, rack, slot)
    try:
        code = ROLE_CODES[role]
    except KeyError:
        raise ValueError(f"unknown role {role!r}") from None
    return f"{s.code.lower()}-{code}-r{rack:02d}-s{slot:02d}"


def bmc_address(site: str, rack: int, slot: int) -> str:
    """IPv4 address of the BMC of the node in this rack position (R-6.4)."""
    s = get_site(site)
    check_position(s, rack, slot)
    return f"10.{s.octet}.{rack}.{slot + 10}"


def bmc_gateway(site: str, rack: int) -> str:
    """Default gateway of the BMC subnet of a rack (R-6.5)."""
    s = get_site(site)
    check_position(s, rack, 1)
    return f"10.{s.octet}.{rack}.1"


def vlan_id(site: str, rack: int, network: str) -> int:
    """VLAN ID of the data or storage network of a rack (R-13.2, R-13.3)."""
    s = get_site(site)
    check_position(s, rack, 1)
    if network == "data":
        return 1000 + rack
    if network == "storage":
        return 3000 + rack
    raise ValueError(f"no rack VLAN for network {network!r}")


def mtu(site: str, network: str) -> int:
    """Interface MTU of a node on a network (R-11.2)."""
    get_site(site)
    if network not in NETWORKS:
        raise ValueError(f"unknown network {network!r}")
    if network in ("data", "storage"):
        return 9000
    return 1500


def node_plan(node: Node) -> dict:
    """All values for one node, in the format of the provisioning pipeline."""
    return {
        "hostname": hostname(node.site, node.rack, node.slot, node.role),
        "bmc": {
            "address": bmc_address(node.site, node.rack, node.slot),
            "prefix": 24,
            "gateway": bmc_gateway(node.site, node.rack),
            "mtu": mtu(node.site, "bmc"),
        },
        "interfaces": {
            network: {"vlan": vlan_id(node.site, node.rack, network), "mtu": mtu(node.site, network)}
            for network in ("data", "storage")
        },
        "mgmt_mtu": mtu(node.site, "mgmt"),
    }
