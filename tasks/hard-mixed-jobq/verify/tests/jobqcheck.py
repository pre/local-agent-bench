"""Helpers of the hidden check: start the server, HTTP requests, and a small
"kubelet" that runs the server with the environment, the files and the ports
of the rendered Deployment.

Environment (set by verify.sh):
  JOBQ_SERVER_BIN      the built server binary
  JOBQ_WORK            the workspace (/work)
  JOBQ_RENDERED_DIR    the parent directory of the rendered manifests (<env>/)
  JOBQ_CHECK_TOKEN     the token that verify.sh gave to deploy.sh
"""

import base64
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

SERVER_BIN = os.environ.get("JOBQ_SERVER_BIN", "/tmp/jobq-check/jobq-server")
WORK = os.environ.get("JOBQ_WORK", "/work")
RENDERED_DIR = os.environ.get("JOBQ_RENDERED_DIR", "/tmp/jobq-check/rendered")
CHECK_TOKEN = os.environ.get("JOBQ_CHECK_TOKEN", "")

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Response:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    def json(self):
        return json.loads(self.body)

    @property
    def content_type(self):
        return self.headers.get("Content-Type", "")


def http(method, url, token=None, body=None, raw=None, timeout=5.0):
    """Send one request. Return a Response, also for an error status."""
    headers = {}
    data = None
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    elif raw is not None:
        data = raw.encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _opener.open(req, timeout=timeout) as resp:
            return Response(resp.status, resp.headers, resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        with e:
            return Response(e.code, e.headers, e.read().decode("utf-8", "replace"))


def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_ports_free(ports, limit=10.0):
    end = time.monotonic() + limit
    while any(port_open(p) for p in ports):
        if time.monotonic() > end:
            raise AssertionError(f"ports still in use: {ports}")
        time.sleep(0.1)


class Server:
    """A running server process."""

    def __init__(self, env, args=(), cwd=None):
        self.log = tempfile.NamedTemporaryFile(prefix="jobq-server-", suffix=".log", delete=False)
        full_env = {"PATH": "/usr/local/bin:/usr/bin:/bin"}
        full_env.update(env)
        self.proc = subprocess.Popen([SERVER_BIN, *args], env=full_env, cwd=cwd or tempfile.gettempdir(),
                                     stdout=self.log, stderr=subprocess.STDOUT)

    def wait_http(self, port, path="/livez", limit=8.0):
        """Wait until GET path on port answers (any status)."""
        end = time.monotonic() + limit
        while time.monotonic() < end:
            if self.proc.poll() is not None:
                raise AssertionError(f"server exited with status {self.proc.returncode}:\n{self.output()}")
            try:
                return http("GET", f"http://127.0.0.1:{port}{path}", timeout=1.0)
            except OSError:
                time.sleep(0.1)
        raise AssertionError(f"no answer on port {port} after {limit} s:\n{self.output()}")

    def output(self):
        self.log.flush()
        with open(self.log.name, encoding="utf-8", errors="replace") as f:
            return f.read()[-3000:]

    def stop(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(10)
        self.log.close()
        os.unlink(self.log.name)


def write_token_file(text):
    fd, path = tempfile.mkstemp(prefix="jobq-token-")
    os.write(fd, text.encode())
    os.close(fd)
    return path


# --- Go durations -----------------------------------------------------------

_NS = {"ns": 1, "us": 1_000, "\u00b5s": 1_000, "\u03bcs": 1_000, "ms": 10**6, "s": 10**9,
       "m": 60 * 10**9, "h": 3600 * 10**9}
_PART = re.compile(r"(\d+\.?\d*|\.\d+)(ns|us|\u00b5s|\u03bcs|ms|s|m|h)")


def go_duration_ns(text):
    """Nanoseconds of a Go duration text. ValueError if it is not valid."""
    from fractions import Fraction
    s = str(text)
    sign = 1
    if s[:1] in "+-" and s:
        sign = -1 if s[0] == "-" else 1
        s = s[1:]
    if s == "0":
        return 0
    if not s:
        raise ValueError(text)
    total, pos = Fraction(0), 0
    while pos < len(s):
        m = _PART.match(s, pos)
        if not m:
            raise ValueError(text)
        total += Fraction(m.group(1).rstrip(".") or "0") * _NS[m.group(2)]
        pos = m.end()
    return sign * int(total)


# --- Manifests and the mini kubelet -----------------------------------------

def load_manifests(directory):
    """All objects of all YAML files below directory, as dicts."""
    files = sorted(os.path.join(d, f) for d, _, names in os.walk(directory)
                   for f in names if f.endswith((".yaml", ".yml")))
    if not files:
        raise AssertionError(f"no YAML files in {directory}")
    out = subprocess.run(["yq", "ea", "-o=json", "-I=0", "[.]", *files],
                         capture_output=True, text=True, check=True).stdout
    docs = json.loads(out)
    return [d for d in docs if isinstance(d, dict) and d.get("kind")]


def find(objs, kind, name):
    found = [o for o in objs if o.get("kind") == kind and o.get("metadata", {}).get("name") == name]
    if len(found) != 1:
        raise AssertionError(f"expected one {kind} {name}, found {len(found)}")
    return found[0]


def secret_data(secret):
    data = {k: base64.b64decode(v) for k, v in (secret.get("data") or {}).items()}
    data.update({k: v.encode() for k, v in (secret.get("stringData") or {}).items()})
    return data


def configmap_data(cm):
    data = {k: str(v).encode() for k, v in (cm.get("data") or {}).items()}
    data.update({k: base64.b64decode(v) for k, v in (cm.get("binaryData") or {}).items()})
    return data


class Pod:
    """The pod of the Deployment jobq, resolved against the rendered objects."""

    def __init__(self, env_name):
        self.objs = load_manifests(os.path.join(RENDERED_DIR, env_name))
        self.deployment = find(self.objs, "Deployment", "jobq")
        self.template = self.deployment["spec"]["template"]
        containers = self.template["spec"]["containers"]
        named = [c for c in containers if c.get("name") == "server"]
        if len(named) != 1:
            raise AssertionError("the Deployment jobq has no container 'server'")
        self.container = named[0]
        self.labels = self.template.get("metadata", {}).get("labels") or {}
        self.ports = {}
        for p in self.container.get("ports") or []:
            self.ports[p["containerPort"]] = p.get("name")
        self.root = None
        self.env, self.env_source = self._resolve_env()

    def port(self, ref):
        """Resolve a port name or number to a container port number."""
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            return int(ref)
        for number, name in self.ports.items():
            if name == ref:
                return number
        raise AssertionError(f"no container port named {ref!r}")

    def port_named(self, name):
        for number, n in self.ports.items():
            if n == name:
                return number
        raise AssertionError(f"no container port named {name!r}")

    def _object_data(self, kind, name, optional=False):
        try:
            obj = find(self.objs, kind, name)
        except AssertionError:
            if optional:
                return None
            raise
        return secret_data(obj) if kind == "Secret" else configmap_data(obj)

    def _resolve_env(self):
        env, source = {}, {}
        for item in self.container.get("envFrom") or []:
            prefix = item.get("prefix", "")
            for kind, key in (("ConfigMap", "configMapRef"), ("Secret", "secretRef")):
                if key in item:
                    ref = item[key]
                    data = self._object_data(kind, ref["name"], ref.get("optional", False)) or {}
                    for k, v in data.items():
                        env[prefix + k] = v.decode()
                        source[prefix + k] = (kind, ref["name"], k)
        for item in self.container.get("env") or []:
            name = item["name"]
            if "value" in item:
                value = str(item["value"])
                value = re.sub(r"\$\(([A-Za-z_][A-Za-z0-9_]*)\)",
                               lambda m: env.get(m.group(1), m.group(0)), value)
                env[name] = value
                source[name] = ("value", None, None)
                continue
            vf = item.get("valueFrom") or {}
            for kind, key in (("ConfigMap", "configMapKeyRef"), ("Secret", "secretKeyRef")):
                if key in vf:
                    ref = vf[key]
                    data = self._object_data(kind, ref["name"], ref.get("optional", False)) or {}
                    if ref["key"] not in data:
                        if ref.get("optional"):
                            break
                        raise AssertionError(f"{kind} {ref['name']} has no key {ref['key']}")
                    env[name] = data[ref["key"]].decode()
                    source[name] = (kind, ref["name"], ref["key"])
                    break
            else:
                if vf:
                    source[name] = ("other", None, None)
        return env, source

    def mounts(self):
        """List of (mountPath, volume, volumeMount)."""
        volumes = {v["name"]: v for v in self.template["spec"].get("volumes") or []}
        out = []
        for vm in self.container.get("volumeMounts") or []:
            if vm["name"] not in volumes:
                raise AssertionError(f"volumeMount {vm['name']} has no volume")
            out.append((vm["mountPath"].rstrip("/") or "/", volumes[vm["name"]], vm))
        return out

    def _materialize(self):
        """Write the files of the Secret and ConfigMap volumes below a temp root."""
        self.root = tempfile.mkdtemp(prefix="jobq-pod-")
        for path, volume, vm in self.mounts():
            if "secret" in volume:
                data = self._object_data("Secret", volume["secret"]["secretName"],
                                         volume["secret"].get("optional", False)) or {}
                items = volume["secret"].get("items")
            elif "configMap" in volume:
                data = self._object_data("ConfigMap", volume["configMap"]["name"],
                                         volume["configMap"].get("optional", False)) or {}
                items = volume["configMap"].get("items")
            else:
                os.makedirs(self.root + path, exist_ok=True)
                continue
            files = {i["path"]: data[i["key"]] for i in items} if items else dict(data)
            if vm.get("subPath"):
                content = files.get(vm["subPath"])
                if content is None:
                    raise AssertionError(f"subPath {vm['subPath']} is not in volume {vm['name']}")
                os.makedirs(os.path.dirname(self.root + path), exist_ok=True)
                with open(self.root + path, "wb") as f:
                    f.write(content)
                continue
            for rel, content in files.items():
                target = os.path.join(self.root + path, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as f:
                    f.write(content)

    def _rewrite(self, value):
        """Map a path in the container to the temp root (longest mount first)."""
        for path, _, _ in sorted(self.mounts(), key=lambda m: -len(m[0])):
            if value == path or value.startswith(path + "/"):
                return self.root + value
        return value

    def start(self):
        """Start the server with the environment, the files and the args of the pod."""
        self._materialize()
        env = {k: self._rewrite(v) for k, v in self.env.items()}
        args = [self._rewrite(a) for a in (self.container.get("command") or [])[1:]]
        args += [self._rewrite(a) for a in self.container.get("args") or []]
        return Server(env, args=args, cwd=self.root)

    def cleanup(self):
        if self.root:
            shutil.rmtree(self.root, ignore_errors=True)
