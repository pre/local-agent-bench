"""The inference server and the path from the agent container to it.

Only server.mode = "external" exists now: the server runs already. Stage 2 adds
a managed server (start, stop, metrics) behind open_server().
"""

import shutil
import socket
import socketserver
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .config import PROXY, ServerConfig
from .podman import Mount

RELAY_DIR = "/run/llm-eval"
PROXY_BASE_URL = "http://127.0.0.1:8080"

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


class UnixRelay:
    """Copies the bytes of each connection on a Unix socket to a TCP address."""

    def __init__(self, socket_path: Path, host: str, port: int):
        self.socket_path = socket_path
        target = (host, port)

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                try:
                    upstream = socket.create_connection(target, timeout=10)
                except OSError:
                    return
                upstream.settimeout(None)
                back = threading.Thread(target=_pump, args=(upstream, self.request), daemon=True)
                back.start()
                _pump(self.request, upstream)
                back.join()
                upstream.close()

        self.server = socketserver.ThreadingUnixStreamServer(str(socket_path), Handler, bind_and_activate=True)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.socket_path.unlink(missing_ok=True)


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

    def __init__(self, cfg: ServerConfig, scratch: Path):
        self.cfg = cfg
        self.scratch = scratch
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


def open_server(cfg: ServerConfig, scratch: Path) -> ExternalServer:
    """Return the server of the configuration. Use it as a context manager."""
    return ExternalServer(cfg, scratch)
