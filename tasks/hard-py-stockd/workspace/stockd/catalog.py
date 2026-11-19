"""The SKU catalogue: pack sizes for commands that count in packs.

<data>/catalog.json is optional:

    {"skus": {"BOLT-M8": {"pack": 50}, "VALVE-22": {"pack": 6}}}

The events always store units, so a later change of a pack size does not
change stock that was received before.
"""

import json
import logging
from pathlib import Path

from .errors import CommandError, ConfigError

log = logging.getLogger(__name__)


class Catalog:
    def __init__(self, packs: dict[str, int] | None = None):
        self.packs = dict(packs or {})

    @classmethod
    def load(cls, path: Path) -> "Catalog":
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            packs = {sku: entry["pack"] for sku, entry in raw["skus"].items()}
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise ConfigError(f"{path}: bad catalogue: {e}") from None
        for sku, pack in packs.items():
            if type(pack) is not int or pack < 1:
                raise ConfigError(f"{path}: pack size of {sku} must be a positive integer")
        log.debug("catalogue: %d SKUs with a pack size", len(packs))
        return cls(packs)

    def units(self, sku: str, packs: int) -> int:
        size = self.packs.get(sku)
        if size is None:
            raise CommandError(f"no pack size for {sku}")
        return packs * size
