"""Configuration files: one TOML file in configs/ with a [server] and a [client] part."""

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

DEFAULT_IMAGE = "localhost/llm-eval-agent:latest"
PROXY = "proxy"
MANAGED_CONTAINER = "llm-eval-server"
CA_FILE = "/etc/ssl/certs/ca-certificates.crt"

# llama-server flags that the harness sets itself for a managed server.
HARNESS_FLAGS = {"--host", "--port", "--api-key-file", "-m", "--model", "-a", "--alias", "-c", "--ctx-size",
                 "--chat-template-file", "-md", "--model-draft", "--spec-draft-model"}

COMMON_KEYS = {"mode", "api_key_file", "model", "context_tokens", "health_path", "agent_network", "agent_url"}
EXTERNAL_KEYS = COMMON_KEYS | {"url", "container"}
MANAGED_KEYS = COMMON_KEYS | {"image", "models_dir", "model_file", "port", "args", "draft", "chat_template",
                              "gtt_max_used_mib", "gtt_min_margin_mib", "mem_available_min_mib", "start_timeout_s"}
REMOTE_KEYS = {"mode", "url", "model", "context_tokens", "agent_network", "ca_file"}

# A value of an args table: true gives the flag alone, false leaves the flag out.
Args = dict[str, str | int | float | bool]


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class DraftConfig:
    model_file: str  # below models_dir
    args: Args = field(default_factory=dict)


@dataclass(frozen=True)
class ManagedConfig:
    """A llama-server container that the harness starts and stops."""
    image: str  # pinned by digest
    models_dir: Path  # mounted read-only at /models
    model_file: str  # below models_dir
    port: int  # host port on 127.0.0.1
    args: Args = field(default_factory=dict)
    draft: DraftConfig | None = None
    chat_template: str | None = None  # below templates/ of the repository
    gtt_max_used_mib: int = 12288
    gtt_min_margin_mib: int = 4096  # the server stops when GTT total minus GTT used is less
    mem_available_min_mib: int = 2048  # the server stops when MemAvailable is less. 0: no limit
    start_timeout_s: int = 900


@dataclass(frozen=True)
class ServerConfig:
    mode: str
    url: str
    api_key_file: Path | None  # None for a remote endpoint: its keys come from client.secrets
    model: str  # the model ID for Claude Code, and --alias of a managed server
    # CLAUDE_CODE_MAX_CONTEXT_TOKENS, and -c of a managed server. Optional for a remote endpoint.
    context_tokens: int | None
    health_path: str = "/health"
    # "proxy": the agent container has no network and reaches the server through
    # a Unix socket relay of the harness. Any other value is a podman --network
    # value, and agent_url is then the server URL in the agent container.
    agent_network: str = PROXY
    agent_url: str | None = None
    container: str | None = None  # the server container, for its log
    managed: ManagedConfig | None = None
    ca_file: Path = Path(CA_FILE)  # remote endpoint: the CA bundle for the agent container


@dataclass(frozen=True)
class ProfileSecrets:
    """Environment variables that the harness reads from a shell profile at run time."""
    from_profile: Path
    names: tuple[str, ...]


@dataclass(frozen=True)
class ClientConfig:
    image: str = DEFAULT_IMAGE
    config_dir: str = "client-config"
    env: dict[str, str] = field(default_factory=dict)
    secrets: ProfileSecrets | None = None


@dataclass(frozen=True)
class Config:
    name: str
    path: Path
    sha256: str
    server: ServerConfig
    client: ClientConfig
    raw: dict[str, Any]


def load_config(path: Path) -> Config:
    path = Path(path).resolve()
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


def _read_merged(path: Path, seen: tuple[Path, ...] = ()) -> dict[str, Any]:
    """Read a configuration file. A "base" key names a file (relative to this
    one) that gives the values that this file does not change. The name of
    the base file is not inherited."""
    if path in seen:
        raise ConfigError(f"{path}: the base files make a loop")
    if not path.is_file():
        raise ConfigError(f"{path}: file not found")
    with path.open("rb") as f:
        raw = tomllib.load(f)
    if "base" not in raw:
        return raw
    base = _read_merged((path.parent / raw.pop("base")).resolve(), (*seen, path))
    base.pop("name", None)
    return _merge(base, raw)


def _merge(base: dict[str, Any], change: dict[str, Any]) -> dict[str, Any]:
    """Tables merge key by key. Lists and scalars of `change` replace those of `base`."""
    merged = dict(base)
    for key, value in change.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _sha256(raw: dict[str, Any]) -> str:
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _server(raw: dict[str, Any]) -> ServerConfig:
    mode = _require(raw, "server.", "mode")
    if mode not in ("external", "managed", "remote"):
        raise ConfigError(f"server.mode must be 'external', 'managed' or 'remote', not {mode!r}")
    if mode == "remote":
        return _remote(raw)
    _check_keys(raw, "server.", EXTERNAL_KEYS if mode == "external" else MANAGED_KEYS)
    for key in ("api_key_file", "model", "context_tokens"):
        _require(raw, "server.", key)
    values = {key: raw[key] for key in COMMON_KEYS & raw.keys()}
    values["api_key_file"] = Path(raw["api_key_file"]).expanduser()
    if mode == "external":
        server = ServerConfig(**values, url=_require(raw, "server.", "url"), container=raw.get("container"))
    else:
        managed = _managed(raw)
        server = ServerConfig(**values, url=f"http://127.0.0.1:{managed.port}", container=MANAGED_CONTAINER,
                              managed=managed)
    if server.agent_network != PROXY and not server.agent_url:
        raise ConfigError("server.agent_url is necessary when server.agent_network is not 'proxy'")
    return server


def _remote(raw: dict[str, Any]) -> ServerConfig:
    _check_keys(raw, "server.", REMOTE_KEYS)
    url = _require(raw, "server.", "url")
    if urlsplit(url).scheme != "https":
        raise ConfigError(f"server.url of a remote endpoint must start with https://, not {url!r}")
    return ServerConfig(mode="remote", url=url, api_key_file=None, model=_require(raw, "server.", "model"),
                        context_tokens=raw.get("context_tokens"), agent_network=raw.get("agent_network", PROXY),
                        ca_file=Path(raw.get("ca_file", CA_FILE)).expanduser())


def _managed(raw: dict[str, Any]) -> ManagedConfig:
    for key in ("image", "models_dir", "model_file", "port"):
        _require(raw, "server.", key)
    if "@sha256:" not in raw["image"]:
        raise ConfigError("server.image must be pinned by digest (name@sha256:...)")
    template = raw.get("chat_template")
    if template is not None:
        parts = PurePosixPath(template).parts
        if parts[0] != "templates" or ".." in parts:
            raise ConfigError(f"server.chat_template must be a path below templates/, not {template!r}")
    draft = raw.get("draft", {})
    _check_keys(draft, "server.draft.", {"model_file", "args"})
    _check_args(raw.get("args", {}), "server.args")
    _check_args(draft.get("args", {}), "server.draft.args")
    for key in ("gtt_max_used_mib", "gtt_min_margin_mib", "mem_available_min_mib"):
        if key in raw and type(raw[key]) is not int:  # bool is a subclass of int: refuse true and false too
            raise ConfigError(f"server.{key} must be an integer (MiB), not {raw[key]!r}")
    values = {key: raw[key] for key in MANAGED_KEYS & raw.keys() & ManagedConfig.__dataclass_fields__.keys()}
    values["models_dir"] = Path(raw["models_dir"]).expanduser()
    values["draft"] = DraftConfig(draft["model_file"], draft.get("args", {})) if draft.get("model_file") else None
    return ManagedConfig(**values)


def _check_args(args: Args, prefix: str) -> None:
    if not isinstance(args, dict):
        raise ConfigError(f"{prefix} must be a table of flag = value")
    reserved = sorted(HARNESS_FLAGS & args.keys())
    if reserved:
        raise ConfigError(f"{prefix}: the harness sets {', '.join(reserved)}")


def _client(raw: dict[str, Any]) -> ClientConfig:
    _check_keys(raw, "client.", {"image", "config_dir", "env", "secrets"})
    env = {key: str(value) for key, value in raw.get("env", {}).items()}
    return ClientConfig(**{**raw, "env": env, "secrets": _secrets(raw.get("secrets"))})


def _secrets(raw: dict[str, Any] | None) -> ProfileSecrets | None:
    if raw is None:
        return None
    _check_keys(raw, "client.secrets.", {"from_profile", "names"})
    return ProfileSecrets(Path(_require(raw, "client.secrets.", "from_profile")).expanduser(),
                          tuple(_require(raw, "client.secrets.", "names")))


def _require(raw: dict[str, Any], prefix: str, key: str) -> Any:
    if key not in raw:
        raise ConfigError(f"{prefix}{key} is missing")
    return raw[key]


def _check_keys(raw: dict[str, Any], prefix: str, allowed: set[str]) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConfigError(f"unknown keys: {', '.join(prefix + k for k in unknown)}")
