"""Hidden tests of the deploy script and the rendered manifests (contract
version 2, rules 5 and 15 to 19). The pod tests start the real server with the
environment, the files and the ports of the rendered Deployment."""

import base64
import json
import os
import subprocess
import tempfile
import unittest

from jobqcheck import CHECK_TOKEN, RENDERED_DIR, WORK, Pod, find, go_duration_ns, http, load_manifests, \
    secret_data, wait_ports_free, write_token_file

ENVS = {
    "staging": {"JOBQ_MAX_TIMEOUT": "1h", "JOBQ_QUEUE_LIMIT": "500", "JOBQ_DRAIN_DELAY": "5s"},
    "production": {"JOBQ_MAX_TIMEOUT": "6h", "JOBQ_QUEUE_LIMIT": "2000", "JOBQ_DRAIN_DELAY": "20s"},
}
API_PORT, METRICS_PORT = 7070, 9102


def deploy(*args):
    return subprocess.run(["bash", os.path.join(WORK, "deploy/deploy.sh"), *args], capture_output=True,
                          text=True, timeout=60, cwd=WORK, stdin=subprocess.DEVNULL)


class RenderTest(unittest.TestCase):
    """Rule 15."""

    def test_both_environments_render(self):
        for env in ENVS:
            self.assertTrue(os.path.isdir(os.path.join(RENDERED_DIR, env)), f"{env} was not rendered")
            load_manifests(os.path.join(RENDERED_DIR, env))

    def test_token_file_required(self):
        empty = write_token_file(" \n\t\n")
        try:
            for args in [[], ["--token-file", "/tmp/jobq-no-such-token"], ["--token-file", empty]]:
                with tempfile.TemporaryDirectory() as out:
                    proc = deploy("--env", "staging", *args, "--render-only", out)
                    self.assertNotEqual(proc.returncode, 0, f"{args}: exit status 0")
        finally:
            os.unlink(empty)

    def test_secret(self):
        for env in ENVS:
            objs = load_manifests(os.path.join(RENDERED_DIR, env))
            data = secret_data(find(objs, "Secret", "jobq-api-token"))
            self.assertIn("token", data)
            self.assertEqual(data["token"].decode().strip(), CHECK_TOKEN)

    def test_token_only_in_secret(self):
        forms = {CHECK_TOKEN}
        for raw in (CHECK_TOKEN, CHECK_TOKEN + "\n"):
            forms.add(base64.b64encode(raw.encode()).decode())
        for env in ENVS:
            for obj in load_manifests(os.path.join(RENDERED_DIR, env)):
                if obj["kind"] == "Secret" and obj["metadata"]["name"] == "jobq-api-token":
                    continue
                text = json.dumps(obj)
                for form in forms:
                    self.assertNotIn(form, text, f"{env}: the token is in {obj['kind']} {obj['metadata']['name']}")

    def test_image_tag(self):
        for env in ENVS:
            pod = Pod(env)
            self.assertTrue(pod.container["image"].endswith(":2.0.0"), pod.container["image"])


class PodCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        wait_ports_free([API_PORT, METRICS_PORT])
        cls.pod = Pod("staging")
        cls.server = cls.pod.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.pod.cleanup()

    def probe(self, kind):
        probe = self.pod.container.get(kind)
        self.assertIsNotNone(probe, f"no {kind}")
        get = probe.get("httpGet")
        self.assertIsNotNone(get, f"{kind} is not httpGet")
        return get.get("path", "/"), self.pod.port(get["port"])


class PodStartsTest(PodCase):
    """Rules 4 and 17: the pod becomes ready with the rendered values."""

    def test_named_ports(self):
        self.assertEqual(self.pod.port_named("api"), API_PORT)
        self.assertEqual(self.pod.port_named("metrics"), METRICS_PORT)

    def test_probes(self):
        for kind, want in [("readinessProbe", "/readyz"), ("livenessProbe", "/livez")]:
            path, port = self.probe(kind)
            self.assertEqual((path, port), (want, API_PORT), kind)
            resp = self.server.wait_http(port, path)
            self.assertEqual(resp.status, 200, f"{kind} {path} on {port}: {resp.status}")


class ServiceTest(PodCase):
    """Rule 17: the Service reaches the API with the token of the Secret."""

    def test_service_routes_to_api(self):
        service = find(self.pod.objs, "Service", "jobq")
        selector = service["spec"].get("selector") or {}
        self.assertTrue(selector, "the Service has no selector")
        for k, v in selector.items():
            self.assertEqual(self.pod.labels.get(k), v, f"selector {k}={v} does not select the pod")
        ports = [p for p in service["spec"]["ports"] if p.get("name") == "http"]
        self.assertEqual(len(ports), 1, service["spec"]["ports"])
        self.assertEqual(ports[0]["port"], 80)
        target = self.pod.port(ports[0].get("targetPort", ports[0]["port"]))
        self.assertEqual(target, API_PORT)
        self.server.wait_http(target)
        token = secret_data(find(self.pod.objs, "Secret", "jobq-api-token"))["token"].decode().strip()
        resp = http("POST", f"http://127.0.0.1:{target}/v2/jobs", token, {"command": ["true"], "timeout": "1h"})
        self.assertEqual(resp.status, 201, resp.body)
        resp = http("POST", f"http://127.0.0.1:{target}/v2/jobs", token,
                    {"command": ["true"], "timeout": "1h0m1s"})
        self.assertEqual(resp.status, 400, "the maximum timeout of staging is not 1h")
        resp = http("GET", f"http://127.0.0.1:{target}/v2/jobs", token)
        self.assertEqual(resp.status, 200, resp.body)
        self.assertEqual(len(resp.json()["jobs"]), 1)


class MetricsScrapeTest(PodCase):
    """Rule 17: the annotations point to the metrics listener."""

    def test_annotations(self):
        annotations = self.pod.template.get("metadata", {}).get("annotations") or {}
        port = int(annotations.get("prometheus.io/port", "0"))
        self.assertEqual(port, self.pod.port_named("metrics"))
        self.assertEqual(annotations.get("prometheus.io/path"), "/metrics")
        self.server.wait_http(API_PORT)
        resp = http("GET", f"http://127.0.0.1:{port}/metrics")
        self.assertEqual(resp.status, 200)
        self.assertIn("jobq_jobs_created_total", resp.body)


class NetworkPolicyTest(unittest.TestCase):
    """Rule 17: ingress only on the two container ports."""

    def test_ports(self):
        for env in ENVS:
            pod = Pod(env)
            np = find(pod.objs, "NetworkPolicy", "jobq")
            for k, v in (np["spec"].get("podSelector", {}).get("matchLabels") or {}).items():
                self.assertEqual(pod.labels.get(k), v)
            ports = set()
            for rule in np["spec"].get("ingress") or []:
                self.assertTrue(rule.get("ports"), f"{env}: an ingress rule allows all ports")
                for p in rule["ports"]:
                    ports.add(pod.port(p["port"]))
            self.assertEqual(ports, {API_PORT, METRICS_PORT}, env)


class TokenMountTest(unittest.TestCase):
    """Rule 18."""

    def test_mount(self):
        for env in ENVS:
            pod = Pod(env)
            path = pod.env.get("JOBQ_TOKEN_FILE")
            self.assertTrue(path, f"{env}: JOBQ_TOKEN_FILE is not set")
            mounts = [(p, v, vm) for p, v, vm in pod.mounts()
                      if v.get("secret", {}).get("secretName") == "jobq-api-token"]
            self.assertEqual(len(mounts), 1, f"{env}: the Secret is not mounted once")
            mount_path, volume, vm = mounts[0]
            self.assertTrue(vm.get("readOnly"), f"{env}: the token volume is not read-only")
            self.assertTrue(path.startswith(mount_path + "/") or path == mount_path,
                            f"{env}: {path} is not in {mount_path}")
            for name, value in pod.env.items():
                self.assertNotEqual(value.strip(), CHECK_TOKEN, f"{env}: the token is in {name}")
            for name, (kind, obj, _) in pod.env_source.items():
                self.assertFalse(kind == "Secret" and obj == "jobq-api-token", f"{env}: {name} reads the Secret")


class ConfigTest(unittest.TestCase):
    """Rules 16 and 19."""

    def test_values_from_configmap(self):
        for env, want in ENVS.items():
            pod = Pod(env)
            for name in ["JOBQ_PORT", "JOBQ_MAX_TIMEOUT_SECONDS"]:
                self.assertNotIn(name, pod.env, f"{env}: {name} is set")
            for name, value in want.items():
                self.assertIn(name, pod.env, f"{env}: {name} is not set")
                kind, obj, _ = pod.env_source[name]
                self.assertEqual((kind, obj), ("ConfigMap", "jobq-config"), f"{env}: source of {name}")
                if name == "JOBQ_QUEUE_LIMIT":
                    self.assertEqual(int(pod.env[name]), int(value), f"{env}: {name}")
                else:
                    self.assertEqual(go_duration_ns(pod.env[name]), go_duration_ns(value), f"{env}: {name}")


class GraceTest(unittest.TestCase):
    """Rule 5: terminationGracePeriodSeconds >= drain delay + 10 s."""

    def test_grace(self):
        for env in ENVS:
            pod = Pod(env)
            grace = pod.template["spec"].get("terminationGracePeriodSeconds", 30)
            drain = go_duration_ns(pod.env.get("JOBQ_DRAIN_DELAY", "5s")) / 1e9
            self.assertGreaterEqual(int(grace), drain + 10, f"{env}: grace {grace}, drain {drain}")


if __name__ == "__main__":
    unittest.main()
