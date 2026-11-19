"""Configuration: stockd.toml in the data directory, then command line options."""

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

from .errors import ConfigError

CONFIG_FILE = "stockd.toml"


@dataclass(frozen=True)
class Config:
    data_dir: Path
    # A segment file is closed and a new one starts when it has this many bytes.
    segment_max_bytes: int = 64 * 1024
    # The number of snapshot files to keep. Older ones are removed.
    snapshot_keep: int = 2
    # The service remembers the request IDs of this many applied commands.
    request_window: int = 5000
    # Commands with more lines than this are rejected.
    max_receive_lines: int = 50

    @property
    def segments_dir(self) -> Path:
        return self.data_dir / "segments"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def catalog_file(self) -> Path:
        return self.data_dir / "catalog.json"


_INT_KEYS = {f.name for f in fields(Config) if f.name != "data_dir"}
_MINIMUM = {"segment_max_bytes": 256, "snapshot_keep": 1, "request_window": 1, "max_receive_lines": 1}


def load_config(data_dir: Path, overrides: dict | None = None) -> Config:
    values: dict[str, int] = {}
    path = data_dir / CONFIG_FILE
    if path.exists():
        try:
            with path.open("rb") as f:
                raw = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"{path}: {e}") from None
        for key, value in raw.items():
            if key not in _INT_KEYS:
                raise ConfigError(f"{path}: unknown key {key!r}")
            values[key] = value
    for key, value in (overrides or {}).items():
        if value is not None:
            values[key] = value
    for key, value in values.items():
        if type(value) is not int:
            raise ConfigError(f"{key} must be an integer, not {value!r}")
        if value < _MINIMUM[key]:
            raise ConfigError(f"{key} must be at least {_MINIMUM[key]}, not {value}")
    return Config(data_dir=data_dir, **values)
