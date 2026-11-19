"""Configuration files: one TOML file in configs/ with a [server] and a [client] part.

Stage 2 adds "mode = managed" (see _server) and the "base" key (see _read_merged).
"""

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_IMAGE = "localhost/llm-eval-agent:latest"
PROXY = "proxy"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class ServerConfig:
    mode: str
    url: str
    api_key_file: Path
    model: str
    context_tokens: int
    health_path: str = "/health"
    # "proxy": the agent container has no network and reaches the server through
    # a Unix socket relay of the harness. Any other value is a podman --network
    # value, and agent_url is then the server URL in the agent container.
    agent_network: str = PROXY
    agent_url: str | None = None


@dataclass(frozen=True)
class ClientConfig:
    image: str = DEFAULT_IMAGE
    config_dir: str = "client-config"
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Config:
    name: str
    path: Path
    sha256: str
    server: ServerConfig
    client: ClientConfig
    raw: dict[str, Any]


def load_config(path: Path) -> Config:
    path = Path(path)
    raw = _read_merged(path)
    _check_keys(raw, "", {"name", "server", "client"})
    return Config(
        name=raw.get("name", path.stem),
        path=path,
        sha256=_sha256(raw),
        server=_server(raw.get("server", {})),
        client=_client(raw.get("client", {})),
        raw=raw,
    )


def _read_merged(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        raw = tomllib.load(f)
    if "base" in raw:
        raise ConfigError(f"{path}: the key 'base' is not implemented yet")
    return raw


def _sha256(raw: dict[str, Any]) -> str:
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _server(raw: dict[str, Any]) -> ServerConfig:
    _check_keys(raw, "server.", {f.name for f in ServerConfig.__dataclass_fields__.values()})
    mode = _require(raw, "server.", "mode")
    if mode == "managed":
        raise ConfigError("server.mode 'managed' is not implemented yet")
    if mode != "external":
        raise ConfigError(f"server.mode must be 'external', not {mode!r}")
    values = dict(raw)
    values["api_key_file"] = Path(_require(raw, "server.", "api_key_file")).expanduser()
    for key in ("url", "model", "context_tokens"):
        _require(raw, "server.", key)
    server = ServerConfig(**values)
    if server.agent_network != PROXY and not server.agent_url:
        raise ConfigError("server.agent_url is necessary when server.agent_network is not 'proxy'")
    return server


def _client(raw: dict[str, Any]) -> ClientConfig:
    _check_keys(raw, "client.", {"image", "config_dir", "env"})
    env = {key: str(value) for key, value in raw.get("env", {}).items()}
    return ClientConfig(**{**raw, "env": env})


def _require(raw: dict[str, Any], prefix: str, key: str) -> Any:
    if key not in raw:
        raise ConfigError(f"{prefix}{key} is missing")
    return raw[key]


def _check_keys(raw: dict[str, Any], prefix: str, allowed: set[str]) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConfigError(f"unknown keys: {', '.join(prefix + k for k in unknown)}")
