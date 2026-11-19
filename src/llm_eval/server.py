"""The inference server and the path from the agent container to it.

server.mode = "external": the server runs already. server.mode = "managed": the
harness starts a llama-server container before the trials and removes it after them.
server.mode = "remote": an HTTPS endpoint (an LLM gateway) that the agent reaches
through an HTTP CONNECT proxy of the harness.
"""

import hashlib
import json
import re
import shutil
import signal
import socket
import socketserver
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .config import MANAGED_CONTAINER, PROXY, Args, ServerConfig
from .podman import Mount
from .sampler import read_gtt_total_mib, read_gtt_used_mib

RELAY_DIR = "/run/llm-eval"
PROXY_BASE_URL = "http://127.0.0.1:8080"
REMOTE_CA = "/run/llm-eval-ca.crt"

# Runs in the agent container (network "none"). socat gives Claude Code a TCP
# port on the loopback interface and sends the bytes to the Unix socket of the
# harness relay. The loop waits until socat listens, then starts the command.
PROXY_SCRIPT = f"""
socat TCP-LISTEN:8080,bind=127.0.0.1,fork,reuseaddr UNIX-CONNECT:{RELAY_DIR}/api.sock &
for _ in $(seq 100); do (: </dev/tcp/127.0.0.1/8080) 2>/dev/null && break; sleep 0.05; done
exec "$@"
"""


class ServerError(Exception):
    pass


@dataclass(frozen=True)
class AgentAccess:
    """How the agent container reaches the server."""
    network: str
    base_url: str
    mounts: list[Mount] = field(default_factory=list)
    command_prefix: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


class UnixRelay:
    """Copies the bytes of each connection on a Unix socket to a TCP address."""

    def __init__(self, socket_path: Path, host: str, port: int):
        self.socket_path = socket_path
        self.target = (host, port)
        relay = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                relay.handle(self.request)

        self.server = socketserver.ThreadingUnixStreamServer(str(socket_path), Handler, bind_and_activate=True)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.socket_path.unlink(missing_ok=True)

    def handle(self, client: socket.socket) -> None:
        try:
            upstream = socket.create_connection(self.target, timeout=10)
        except OSError:
            return
        _splice(client, upstream)


class ConnectProxy(UnixRelay):
    """An HTTP proxy on a Unix socket that accepts only "CONNECT host:port" to its
    target. It refuses all other requests with HTTP 403. TLS goes through the
    tunnel from end to end: the proxy does not see the keys."""

    MAX_HEAD = 8192

    def handle(self, client: socket.socket) -> None:
        head, rest = _read_head(client, self.MAX_HEAD)
        method, _, target = head.partition(b"\r\n")[0].decode(errors="replace").partition(" ")
        host, port = self.target
        if method != "CONNECT" or target.split(" ")[0].lower() != f"{host}:{port}".lower():
            client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            return
        try:
            upstream = socket.create_connection(self.target, timeout=10)
        except OSError:
            client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            return
        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        upstream.sendall(rest)
        _splice(client, upstream)


def _read_head(client: socket.socket, limit: int) -> tuple[bytes, bytes]:
    """Read an HTTP request head. Return the head and the bytes after it."""
    data = b""
    while b"\r\n\r\n" not in data and len(data) < limit:
        chunk = client.recv(4096)
        if not chunk:
            break
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    return head, rest


def _splice(client: socket.socket, upstream: socket.socket) -> None:
    """Copy the bytes in the two directions until both sides close."""
    upstream.settimeout(None)
    back = threading.Thread(target=_pump, args=(upstream, client), daemon=True)
    back.start()
    _pump(client, upstream)
    back.join()
    upstream.close()


def _pump(source: socket.socket, dest: socket.socket) -> None:
    try:
        while data := source.recv(65536):
            dest.sendall(data)
    except OSError:
        pass
    try:
        dest.shutdown(socket.SHUT_WR)
    except OSError:
        pass


class ExternalServer:
    """A server that runs already. The harness does not start or stop it."""

    def __init__(self, cfg: ServerConfig, scratch: Path, gtt_total: Callable[[], int] = read_gtt_total_mib):
        self.cfg = cfg
        self.scratch = scratch
        self.gtt_total = gtt_total
        self.relay: UnixRelay | None = None

    def __enter__(self) -> "ExternalServer":
        if self.cfg.agent_network == PROXY:
            relay_dir = self.scratch / "relay"
            relay_dir.mkdir(parents=True, exist_ok=True)
            url = urlsplit(self.cfg.url)
            self.relay = UnixRelay(relay_dir / "api.sock", url.hostname, url.port or 80)
            self.relay.start()
        return self

    def __exit__(self, *exc) -> None:
        if self.relay:
            self.relay.stop()
            shutil.rmtree(self.relay.socket_path.parent, ignore_errors=True)
            self.relay = None

    def api_key(self) -> str:
        return self.cfg.api_key_file.read_text().strip()

    def secret_env(self) -> dict[str, str]:
        """The secret environment of Claude Code for this server."""
        return {"ANTHROPIC_AUTH_TOKEN": self.api_key()}

    def check_health(self) -> None:
        request = urllib.request.Request(
            self.cfg.url + self.cfg.health_path, headers={"Authorization": f"Bearer {self.api_key()}"}
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                status = response.status
        except urllib.error.HTTPError as e:
            status = e.code
        except OSError as e:
            raise ServerError(f"server {self.cfg.url} is not reachable: {e}") from e
        if status != 200:
            raise ServerError(f"server {self.cfg.url}{self.cfg.health_path} gave HTTP {status}")

    def agent_access(self) -> AgentAccess:
        if self.relay:
            return AgentAccess(
                network="none",
                base_url=PROXY_BASE_URL,
                mounts=[Mount(self.relay.socket_path.parent, RELAY_DIR)],
                command_prefix=["bash", "-c", PROXY_SCRIPT, "agent"],
            )
        return AgentAccess(network=self.cfg.agent_network, base_url=self.cfg.agent_url)

    def describe(self) -> dict:
        """The server values for run.json."""
        return {"mode": "external", "url": self.cfg.url, "container": self.cfg.container,
                "gtt_total_mib": self.gtt_total()}


class RemoteServer(ExternalServer):
    """An HTTPS endpoint, for example an LLM gateway. No container, no API key file:
    the keys come from client.secrets. In proxy mode the agent container has no
    network and reaches only the host and port of the endpoint, through a
    ConnectProxy of the harness on the relay socket."""

    def __enter__(self) -> "RemoteServer":
        if self.cfg.agent_network == PROXY:
            relay_dir = self.scratch / "relay"
            relay_dir.mkdir(parents=True, exist_ok=True)
            url = urlsplit(self.cfg.url)
            self.relay = ConnectProxy(relay_dir / "api.sock", url.hostname, url.port or 443)
            self.relay.start()
        return self

    def secret_env(self) -> dict[str, str]:
        return {}

    def check_health(self) -> None:
        """A request without credentials. Each HTTP status shows that the endpoint answers."""
        context = ssl.create_default_context(cafile=str(self.cfg.ca_file))
        try:
            urllib.request.urlopen(self.cfg.url, timeout=10, context=context).close()
        except urllib.error.HTTPError:
            pass
        except OSError as e:
            raise ServerError(f"endpoint {self.cfg.url} is not reachable: {e}") from e

    def agent_access(self) -> AgentAccess:
        ca = Mount(self.cfg.ca_file, REMOTE_CA, readonly=True)
        ca_env = {"NODE_EXTRA_CA_CERTS": REMOTE_CA, "SSL_CERT_FILE": REMOTE_CA}
        if self.relay:
            return AgentAccess(
                network="none",
                base_url=self.cfg.url,
                mounts=[Mount(self.relay.socket_path.parent, RELAY_DIR), ca],
                command_prefix=["bash", "-c", PROXY_SCRIPT, "agent"],
                env={"HTTPS_PROXY": PROXY_BASE_URL, **ca_env},
            )
        return AgentAccess(network=self.cfg.agent_network, base_url=self.cfg.url, mounts=[ca], env=ca_env)

    def describe(self) -> dict:
        return {"mode": "remote", "url": self.cfg.url, "model": self.cfg.model,
                "agent_network": self.cfg.agent_network}


SERVER_LABEL = "llm-eval.role=server"
# The same as the llama-server recipes: crun keeps the host group "render", so
# /dev/kfd opens. ROCm uses NUMA syscalls that the default seccomp profile blocks.
GPU_ARGS = ["--runtime", "crun", "--device", "/dev/kfd", "--device", "/dev/dri/renderD128",
            "--group-add", "keep-groups", "--security-opt", "seccomp=unconfined"]
STOP_TIMEOUT_S = 60
SHARD = re.compile(r"-(\d{5})-of-(\d{5})\.gguf$")


def llama_server_args(cfg: ServerConfig) -> list[str]:
    m = cfg.managed
    args = ["--host", "0.0.0.0", "--port", "8080", "--api-key-file", "/run/api-key",
            "-m", f"/models/{m.model_file}", "--alias", cfg.model, "-c", str(cfg.context_tokens),
            *_flags(m.args)]
    if m.chat_template:
        args += ["--chat-template-file", "/run/chat-template.jinja"]
    if m.draft:
        args += ["-md", f"/models/{m.draft.model_file}", *_flags(m.draft.args)]
    return args


def _flags(args: Args) -> list[str]:
    flags = []
    for flag, value in args.items():
        if value is True:
            flags.append(flag)
        elif value is not False:
            flags += [flag, str(value)]
    return flags


def model_files(models_dir: Path, model_file: str) -> list[dict]:
    """Name and size of the model file. A split GGUF file gives all its parts."""
    shard = SHARD.search(model_file)
    names = [model_file]
    if shard:
        count = shard[2]
        names = [SHARD.sub(f"-{i:05d}-of-{count}.gguf", model_file) for i in range(1, int(count) + 1)]
    files = []
    for name in names:
        path = models_dir / name
        if not path.is_file():
            raise ServerError(f"model file {path} is missing")
        files.append({"name": name, "bytes": path.stat().st_size})
    return files


class ManagedServer(ExternalServer):
    """A llama-server container (llm-eval-server) that the harness starts and removes.

    The harness removes only a container that has its label. The container also
    stops when the body of the with statement raises, Ctrl-C included.
    """

    def __init__(self, cfg: ServerConfig, scratch: Path, podman, root: Path, out_dir: Path,
                 replace: bool = False, gtt_used: Callable[[], int] = read_gtt_used_mib,
                 gtt_total: Callable[[], int] = read_gtt_total_mib, sleep: Callable[[float], None] = time.sleep):
        super().__init__(cfg, scratch, gtt_total)
        self.podman = podman
        self.root = root
        self.out_dir = out_dir
        self.replace = replace
        self.gtt_used = gtt_used
        self.sleep = sleep
        self.started = False
        self.info: dict | None = None

    def __enter__(self) -> "ManagedServer":
        m = self.cfg.managed
        files = model_files(m.models_dir, m.model_file)
        draft_files = model_files(m.models_dir, m.draft.model_file) if m.draft else None
        template = self._template()
        self._clear_name()
        gtt = self._check_gtt()
        run_args = self._run_args()
        self.started = True
        try:
            began = time.monotonic()
            code, out = self.podman.call(run_args)
            if code != 0:
                raise ServerError(f"podman run of {MANAGED_CONTAINER} failed: {out.strip()}")
            self._wait_until_healthy()
            load_seconds = round(time.monotonic() - began, 1)
            after_load = self.gtt_used()
            self.info = {
                "mode": "managed",
                "url": self.cfg.url,
                "container": MANAGED_CONTAINER,
                "image": m.image,
                "image_digest": self._inspect()["ImageDigest"],
                "llama_server_version": self._version(),
                "llama_server_args": llama_server_args(self.cfg),
                "podman_args": run_args,
                "model_files": files,
                "draft_model_files": draft_files,
                "chat_template": template,
                "load_seconds": load_seconds,
                "gtt_used_before_start_mib": gtt,
                "gtt_used_after_load_mib": after_load,
                "gtt_total_mib": self.gtt_total(),
            }
            super().__enter__()
        except BaseException:
            self._remove()
            raise
        return self

    def __exit__(self, *exc) -> None:
        self._remove()
        super().__exit__(*exc)

    def describe(self) -> dict:
        return self.info

    def _template(self) -> dict | None:
        name = self.cfg.managed.chat_template
        if not name:
            return None
        path = self.root / name
        if not path.is_file():
            raise ServerError(f"chat template {path} is missing")
        return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def _run_args(self) -> list[str]:
        m = self.cfg.managed
        volumes = [f"{m.models_dir}:/models:ro", f"{self.cfg.api_key_file}:/run/api-key:ro"]
        if m.chat_template:
            volumes.append(f"{self.root / m.chat_template}:/run/chat-template.jinja:ro")
        args = ["run", "-d", "--name", MANAGED_CONTAINER, "--label", SERVER_LABEL, *GPU_ARGS,
                "-p", f"127.0.0.1:{m.port}:8080"]
        for volume in volumes:
            args += ["-v", volume]
        return [*args, m.image, "llama-server", *llama_server_args(self.cfg)]

    def _inspect(self) -> dict | None:
        code, out = self.podman.call(["container", "inspect", MANAGED_CONTAINER])
        return json.loads(out)[0] if code == 0 else None

    def _clear_name(self) -> None:
        info = self._inspect()
        if info is None:
            return
        if (info["Config"].get("Labels") or {}).get("llm-eval.role") != "server":
            raise ServerError(f"a container {MANAGED_CONTAINER} exists and the harness did not start it. "
                              "The harness does not remove it.")
        if not self.replace:
            raise ServerError(f"the container {MANAGED_CONTAINER} ({info['State']['Status']}) remains from an "
                              f"earlier run of the harness. Examine it (podman logs {MANAGED_CONTAINER}), "
                              "then use --replace to remove it.")
        self.podman.call(["stop", "-t", str(STOP_TIMEOUT_S), MANAGED_CONTAINER])
        self.podman.call(["rm", MANAGED_CONTAINER])

    def _check_gtt(self) -> int:
        used, limit = self.gtt_used(), self.cfg.managed.gtt_max_used_mib
        if used > limit:
            _, containers = self.podman.call(["ps", "--format", "{{.Names}}  {{.Image}}  {{.Status}}"])
            raise ServerError(f"GTT used is {used} MiB, more than server.gtt_max_used_mib = {limit} MiB. "
                              "Another GPU load runs. Stop it yourself, the harness does not stop it. "
                              f"Running containers:\n{containers.rstrip()}")
        return used

    def _wait_until_healthy(self) -> None:
        timeout = self.cfg.managed.start_timeout_s
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.check_health()
                return
            except ServerError as e:
                problem = e
            info = self._inspect()
            if not (info and info["State"]["Running"]):
                _, log = self.podman.call(["logs", "--tail", "20", MANAGED_CONTAINER])
                raise ServerError(f"{MANAGED_CONTAINER} stopped during the start. The end of its log:\n{log}")
            if time.monotonic() >= deadline:
                raise ServerError(f"{MANAGED_CONTAINER} is not healthy after {timeout} s: {problem}")
            self.sleep(1)

    def _version(self) -> str | None:
        """The build line of llama-server. The log does not have it at the default verbosity."""
        _, out = self.podman.call(["run", "--rm", "--network=none", self.cfg.managed.image,
                                   "llama-server", "--version"])
        return next((line for line in out.splitlines() if "build" in line), None)

    def _remove(self) -> None:
        """Stop the container, save its full log as server.log in the run directory, remove it.

        SIGINT is ignored meanwhile (podman inherits this): `uv run` sends a second
        SIGINT after Ctrl-C, and it must not stop the cleanup.
        """
        if not self.started:
            return
        self.started = False
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            print(f"llm-eval: stopping {MANAGED_CONTAINER}", file=sys.stderr, flush=True)
            self.podman.call(["stop", "-t", str(STOP_TIMEOUT_S), MANAGED_CONTAINER])
            _, log = self.podman.call(["logs", MANAGED_CONTAINER])
            self.out_dir.mkdir(parents=True, exist_ok=True)
            (self.out_dir / "server.log").write_text(log.replace(self.api_key(), "<redacted>"))
            code, out = self.podman.call(["rm", MANAGED_CONTAINER])
            if code != 0:
                print(f"llm-eval: could not remove {MANAGED_CONTAINER}: {out.strip()}", file=sys.stderr)
        finally:
            signal.signal(signal.SIGINT, previous)


def open_server(cfg: ServerConfig, scratch: Path, podman=None, root: Path | None = None,
                out_dir: Path | None = None, replace: bool = False, **host) -> ExternalServer:
    """Return the server of the configuration. Use it as a context manager. `host`
    replaces the functions that read GTT (and sleep for a managed server) in tests."""
    if cfg.managed:
        return ManagedServer(cfg, scratch, podman, root, out_dir, replace, **host)
    if cfg.mode == "remote":
        return RemoteServer(cfg, scratch)
    return ExternalServer(cfg, scratch, **host)
