import http.server
import socket
import threading
from pathlib import Path

import pytest

from llm_eval.config import CA_FILE, ServerConfig
from llm_eval.server import (PROXY_BASE_URL, REMOTE_CA, ConnectProxy, ExternalServer, RemoteServer, ServerError,
                             UnixRelay, open_server)


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


@pytest.fixture
def echo_port():
    """A TCP server on the loopback interface that sends back each byte it gets."""
    listener = socket.create_server(("127.0.0.1", 0))

    def serve():
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            with conn:
                while data := conn.recv(4096):
                    conn.sendall(data)

    threading.Thread(target=serve, daemon=True).start()
    yield listener.getsockname()[1]
    listener.close()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def proxy_request(socket_path: Path, request: bytes, payload: bytes = b"") -> bytes:
    """Send a request to the proxy. After a 200 reply, send the payload and read the echo."""
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(5)
        client.connect(str(socket_path))
        client.sendall(request)
        reply = client.recv(4096)
        if reply.startswith(b"HTTP/1.1 200") and payload:
            client.sendall(payload)
            echo = b""
            while len(echo) < len(payload):
                echo += client.recv(4096)
            return reply + echo
        while chunk := client.recv(4096):
            reply += chunk
        return reply


@pytest.fixture
def connect_proxy(tmp_path, echo_port):
    proxy = ConnectProxy(tmp_path / "p.sock", "127.0.0.1", echo_port)
    proxy.start()
    yield proxy
    proxy.stop()


def test_connect_proxy_tunnels_to_the_allowed_target(connect_proxy, echo_port):
    request = f"CONNECT 127.0.0.1:{echo_port} HTTP/1.1\r\nHost: 127.0.0.1:{echo_port}\r\n\r\n".encode()

    reply = proxy_request(connect_proxy.socket_path, request, b"tls bytes")

    assert reply == b"HTTP/1.1 200 Connection Established\r\n\r\ntls bytes"


@pytest.mark.parametrize("request_line", [
    "CONNECT example.org:443 HTTP/1.1",
    "CONNECT 127.0.0.1:1 HTTP/1.1",
    "GET http://127.0.0.1:{port}/ HTTP/1.1",
    "nonsense",
])
def test_connect_proxy_refuses_other_targets(connect_proxy, echo_port, request_line):
    request = request_line.format(port=echo_port).encode() + b"\r\nHost: x\r\n\r\n"

    reply = proxy_request(connect_proxy.socket_path, request)

    assert reply.startswith(b"HTTP/1.1 403 Forbidden\r\n")


def test_connect_proxy_target_not_reachable(tmp_path):
    port = free_port()
    proxy = ConnectProxy(tmp_path / "p.sock", "127.0.0.1", port)
    proxy.start()
    try:
        reply = proxy_request(proxy.socket_path, f"CONNECT 127.0.0.1:{port} HTTP/1.1\r\n\r\n".encode())
    finally:
        proxy.stop()

    assert reply.startswith(b"HTTP/1.1 502 Bad Gateway\r\n")


def remote_config(url: str = "https://gateway.example.org/api", **kw) -> ServerConfig:
    return ServerConfig(mode="remote", url=url, api_key_file=None, model="Claude-Test-1", context_tokens=None, **kw)


def test_remote_proxy_access(tmp_path):
    with open_server(remote_config(), tmp_path) as server:
        access = server.agent_access()
        assert access.network == "none"
        assert access.base_url == "https://gateway.example.org/api"
        assert access.command_prefix[:2] == ["bash", "-c"]
        relay, ca = access.mounts
        assert relay.container == "/run/llm-eval"
        assert (relay.host / "api.sock").is_socket()
        assert (ca.host, ca.container, ca.readonly) == (Path(CA_FILE), REMOTE_CA, True)
        assert access.env == {"HTTPS_PROXY": PROXY_BASE_URL, "NODE_EXTRA_CA_CERTS": REMOTE_CA,
                              "SSL_CERT_FILE": REMOTE_CA}
        assert isinstance(server.relay, ConnectProxy)
        assert server.relay.target == ("gateway.example.org", 443)
        assert server.secret_env() == {}
        assert server.describe() == {"mode": "remote", "url": "https://gateway.example.org/api",
                                     "model": "Claude-Test-1", "agent_network": "proxy"}

    assert not (relay.host / "api.sock").exists()


def test_remote_podman_network_access(tmp_path):
    with open_server(remote_config(agent_network="slirp4netns"), tmp_path) as server:
        access = server.agent_access()

    assert access.network == "slirp4netns"
    assert access.base_url == "https://gateway.example.org/api"
    assert [m.container for m in access.mounts] == [REMOTE_CA]
    assert access.command_prefix == []
    assert access.env == {"NODE_EXTRA_CA_CERTS": REMOTE_CA, "SSL_CERT_FILE": REMOTE_CA}


def test_remote_check_health_accepts_each_http_status(tmp_path, http_server):
    # The request has no credentials: the 401 of the test server shows that the endpoint answers.
    RemoteServer(remote_config(http_server), tmp_path).check_health()


def test_remote_check_health_not_reachable(tmp_path):
    with pytest.raises(ServerError, match="not reachable"):
        RemoteServer(remote_config(f"http://127.0.0.1:{free_port()}"), tmp_path).check_health()


def test_local_server_gives_its_key_as_auth_token(tmp_path):
    server = ExternalServer(config(tmp_path, "http://127.0.0.1:1"), tmp_path)

    assert server.secret_env() == {"ANTHROPIC_AUTH_TOKEN": "k1"}
