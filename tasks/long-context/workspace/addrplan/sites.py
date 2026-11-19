"""Sites of the platform and their address octets (standard section 2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Site:
    code: str
    city: str
    octet: int
    max_rack: int


SITES = {
    "HEL1": Site("HEL1", "Helsinki", 16, 48),
    "HEL2": Site("HEL2", "Vantaa", 17, 64),
    "OUL1": Site("OUL1", "Oulu", 24, 32),
    "TMP1": Site("TMP1", "Tampere", 32, 24),
    "ESP1": Site("ESP1", "Espoo", 40, 36),
}

MAX_SLOT = 42


def get_site(code: str) -> Site:
    try:
        return SITES[code.upper()]
    except KeyError:
        raise ValueError(f"unknown site {code!r}") from None


def check_position(site: Site, rack: int, slot: int) -> None:
    if not 1 <= rack <= site.max_rack:
        raise ValueError(f"{site.code}: rack {rack} is outside 1..{site.max_rack}")
    if not 1 <= slot <= MAX_SLOT:
        raise ValueError(f"slot {slot} is outside 1..{MAX_SLOT}")
