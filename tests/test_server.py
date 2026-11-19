import http.server
import socket
import threading
from pathlib import Path

import pytest

from llm_eval.config import ServerConfig
from llm_eval.server import PROXY_BASE_URL, ExternalServer, ServerError, UnixRelay, open_server


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        ok = self.path == "/health" and self.headers.get("Authorization") == "Bearer k1"
        body = b'{"status":"ok"}' if ok else b"no"
        self.send_response(200 if ok else 401)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def http_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def config(tmp_path: Path, url: str, **kw) -> ServerConfig:
    key = tmp_path / "key"
    key.write_text("k1\n")
    return ServerConfig(mode="external", url=url, api_key_file=key, model="m", context_tokens=1000, **kw)


def test_api_key_is_read_from_file(tmp_path):
    server = ExternalServer(config(tmp_path, "http://127.0.0.1:1"), tmp_path)

    assert server.api_key() == "k1"


def test_check_health_ok(tmp_path, http_server):
    ExternalServer(config(tmp_path, http_server), tmp_path).check_health()


def test_check_health_bad_status(tmp_path, http_server):
    server = ExternalServer(config(tmp_path, http_server, health_path="/other"), tmp_path)

    with pytest.raises(ServerError, match="401"):
        server.check_health()


def test_check_health_no_server(tmp_path):
    with pytest.raises(ServerError, match="not reachable"):
        ExternalServer(config(tmp_path, "http://127.0.0.1:1"), tmp_path).check_health()


def test_proxy_access_relays_to_the_server(tmp_path, http_server):
    with open_server(config(tmp_path, http_server), tmp_path) as server:
        access = server.agent_access()
        assert access.network == "none"
        assert access.base_url == PROXY_BASE_URL
        assert access.command_prefix[:2] == ["bash", "-c"]
        (mount,) = access.mounts
        assert mount.container == "/run/llm-eval"

        client = socket.socket(socket.AF_UNIX)
        client.connect(str(mount.host / "api.sock"))
        client.sendall(b"GET /health HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer k1\r\nConnection: close\r\n\r\n")
        reply = b""
        while chunk := client.recv(4096):
            reply += chunk
        client.close()

    assert reply.startswith(b"HTTP/1.0 200")
    assert reply.endswith(b'{"status":"ok"}')
    assert not (mount.host / "api.sock").exists()


def test_podman_network_access(tmp_path):
    cfg = config(tmp_path, "http://127.0.0.1:8080", agent_network="container:srv", agent_url="http://127.0.0.1:8080")

    with open_server(cfg, tmp_path) as server:
        access = server.agent_access()

    assert access.network == "container:srv"
    assert access.base_url == "http://127.0.0.1:8080"
    assert access.mounts == []
    assert access.command_prefix == []


def test_relay_target_closed(tmp_path):
    # A port with no listener: the relay closes the client connection.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    relay = UnixRelay(tmp_path / "r.sock", "127.0.0.1", port)
    relay.start()
    try:
        client = socket.socket(socket.AF_UNIX)
        client.connect(str(tmp_path / "r.sock"))
        client.settimeout(5)
        assert client.recv(10) == b""
        client.close()
    finally:
        relay.stop()
