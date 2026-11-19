"""Hidden black-box tests of the server process (contract version 2, rules 1 to 11)."""

import os
import re
import signal
import time
import unittest
from datetime import datetime

from jobqcheck import Server, http, wait_ports_free, write_token_file

TOKEN = "srv-Token_7f3a9c"
API, METRICS = 17070, 19102
BASE = f"http://127.0.0.1:{API}"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def start(extra=None, token_text=None, api=API, metrics=METRICS):
    wait_ports_free([api, metrics])
    path = write_token_file(TOKEN + "\n" if token_text is None else token_text)
    env = {
        "JOBQ_API_ADDR": f":{api}",
        "JOBQ_METRICS_ADDR": f":{metrics}",
        "JOBQ_TOKEN_FILE": path,
        "JOBQ_MAX_TIMEOUT": "1h",
        "JOBQ_QUEUE_LIMIT": "1000",
        "JOBQ_DRAIN_DELAY": "0s",
    }
    env.update(extra or {})
    server = Server({k: v for k, v in env.items() if v is not None})
    server.token_path = path
    return server


class ServerCase(unittest.TestCase):
    extra = None
    token_text = None

    @classmethod
    def setUpClass(cls):
        cls.server = start(cls.extra, cls.token_text)
        try:
            cls.server.wait_http(API)
        except AssertionError:
            cls.server.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        os.unlink(cls.server.token_path)

    def create(self, timeout="90s", command=("echo", "hi")):
        return http("POST", BASE + "/v2/jobs", TOKEN, {"command": list(command), "timeout": timeout})

    def assertError(self, resp, status, code):
        self.assertEqual(resp.status, status, resp.body)
        self.assertTrue(resp.content_type.startswith("application/json"), resp.content_type)
        body = resp.json()
        self.assertEqual(set(body), {"error"}, body)
        self.assertEqual(body["error"]["code"], code, body)
        self.assertIsInstance(body["error"]["message"], str)


class StartupTest(unittest.TestCase):
    """Rule 2: refused start."""

    def assertRefused(self, extra=None, token_text=None):
        server = start(extra, token_text)
        try:
            server.proc.wait(5)
        except Exception:
            server.stop()
            self.fail(f"the server did not exit for {extra} {token_text!r}")
        code = server.proc.returncode
        server.stop()
        self.assertNotEqual(code, 0, f"exit status 0 for {extra} {token_text!r}")

    def test_no_token_file_variable(self):
        self.assertRefused({"JOBQ_TOKEN_FILE": None})

    def test_missing_token_file(self):
        self.assertRefused({"JOBQ_TOKEN_FILE": "/tmp/jobq-no-such-token-file"})

    def test_empty_token(self):
        self.assertRefused(token_text=" \n")

    def test_v1_variables(self):
        self.assertRefused({"JOBQ_PORT": "8080"})
        self.assertRefused({"JOBQ_MAX_TIMEOUT_SECONDS": "3600"})

    def test_bad_values(self):
        self.assertRefused({"JOBQ_MAX_TIMEOUT": "3600"})
        self.assertRefused({"JOBQ_QUEUE_LIMIT": "0"})
        self.assertRefused({"JOBQ_DRAIN_DELAY": "soon"})


class DefaultsTest(unittest.TestCase):
    """Rule 1: the default listen addresses."""

    def test_default_ports(self):
        wait_ports_free([7070, 9102])
        path = write_token_file(TOKEN + "\n")
        server = Server({"JOBQ_TOKEN_FILE": path})
        try:
            self.assertEqual(server.wait_http(7070).status, 200)
            self.assertEqual(http("GET", "http://127.0.0.1:9102/metrics").status, 200)
        finally:
            server.stop()
            os.unlink(path)


class RoutesTest(ServerCase):
    """Rules 3, 7 and 8."""

    def test_create_get_cancel(self):
        resp = self.create("90s", ["echo", "a b"])
        self.assertEqual(resp.status, 201, resp.body)
        self.assertTrue(resp.content_type.startswith("application/json"))
        job = resp.json()
        self.assertRegex(job["id"], ID_RE)
        self.assertEqual(job["command"], ["echo", "a b"])
        self.assertEqual(job["timeout"], "1m30s")
        self.assertEqual(job["state"], "queued")
        created = datetime.fromisoformat(re.sub(r"(\.\d{6})\d*", r"\1", job["created_at"]).replace("Z", "+00:00"))
        self.assertEqual(created.utcoffset().total_seconds(), 0)
        self.assertNotIn("timeout_seconds", job)

        got = http("GET", f"{BASE}/v2/jobs/{job['id']}", TOKEN)
        self.assertEqual(got.status, 200, got.body)
        self.assertEqual(got.json(), job)

        cancelled = http("POST", f"{BASE}/v2/jobs/{job['id']}/cancel", TOKEN)
        self.assertEqual(cancelled.status, 200, cancelled.body)
        self.assertEqual(cancelled.json()["state"], "cancelled")
        self.assertEqual(http("GET", f"{BASE}/v2/jobs/{job['id']}", TOKEN).json()["state"], "cancelled")
        again = http("POST", f"{BASE}/v2/jobs/{job['id']}/cancel", TOKEN, {})
        self.assertError(again, 409, "failed_precondition")

        other = self.create().json()
        resp = http("POST", f"{BASE}/v2/jobs/{other['id']}/cancel", TOKEN, {})
        self.assertEqual(resp.status, 200, resp.body)

    def test_unique_ids(self):
        ids = {self.create().json()["id"] for _ in range(30)}
        self.assertEqual(len(ids), 30)
        for job_id in ids:
            self.assertRegex(job_id, ID_RE)

    def test_v1_paths_removed(self):
        self.assertEqual(http("GET", BASE + "/v1/jobs", TOKEN).status, 404)
        self.assertEqual(http("POST", BASE + "/v1/jobs", TOKEN,
                              {"command": ["true"], "timeout_seconds": 5}).status, 404)
        self.assertEqual(http("GET", BASE + "/healthz").status, 404)
        self.assertEqual(http("GET", BASE + "/metrics").status, 404)


class AuthTest(ServerCase):
    """Rule 6. The token file has white space around the token."""

    token_text = " \t" + TOKEN + "\n\n"

    def test_token_required(self):
        self.assertError(http("GET", BASE + "/v2/jobs"), 401, "unauthenticated")
        self.assertError(http("GET", BASE + "/v2/jobs", "wrong"), 401, "unauthenticated")
        self.assertError(http("GET", BASE + "/v2/jobs/j-1", None), 401, "unauthenticated")
        self.assertError(http("POST", BASE + "/v2/jobs", None, {"command": ["true"], "timeout": "5s"}),
                         401, "unauthenticated")
        self.assertError(http("GET", BASE + "/v2/jobs", TOKEN + "x"), 401, "unauthenticated")

    def test_token_accepted(self):
        self.assertEqual(self.create().status, 201)
        self.assertEqual(http("GET", BASE + "/v2/jobs", TOKEN).status, 200)

    def test_probes_and_metrics_without_token(self):
        self.assertEqual(http("GET", BASE + "/livez").status, 200)
        self.assertEqual(http("GET", BASE + "/readyz").status, 200)
        self.assertEqual(http("GET", f"http://127.0.0.1:{METRICS}/metrics").status, 200)


class TimeoutTest(ServerCase):
    """Rule 9 with JOBQ_MAX_TIMEOUT=1h."""

    def test_normalized_text(self):
        cases = {
            "90s": "1m30s",
            "1h": "1h0m0s",
            "60m": "1h0m0s",
            "1500ms": "1.5s",
            "250us": "250µs",
            "0.25ms": "250µs",
            "2m0.5s": "2m0.5s",
            "59m59.999999s": "59m59.999999s",
            "1s": "1s",
        }
        for given, want in cases.items():
            resp = self.create(given)
            self.assertEqual(resp.status, 201, f"{given}: {resp.body}")
            self.assertEqual(resp.json()["timeout"], want, given)

    def test_invalid(self):
        for timeout in ["0s", "0", "-5s", "1h0m0.001s", "61m", "abc", "", "5"]:
            self.assertError(self.create(timeout), 400, "invalid_argument")
        bodies = [
            {"command": ["true"], "timeout": 90},
            {"command": ["true"]},
            {"command": ["true"], "timeout_seconds": 90},
            {"command": ["true"], "timeout": "5s", "priority": 1},
            {"command": [], "timeout": "5s"},
            {"command": "true", "timeout": "5s"},
            {"command": ["true", 3], "timeout": "5s"},
            {"timeout": "5s"},
        ]
        for body in bodies:
            self.assertError(http("POST", BASE + "/v2/jobs", TOKEN, body), 400, "invalid_argument")
        self.assertError(http("POST", BASE + "/v2/jobs", TOKEN, raw="not json"), 400, "invalid_argument")


class PagesTest(ServerCase):
    """Rule 10."""

    def pages(self, size):
        out, token = [], None
        for _ in range(100):
            url = f"{BASE}/v2/jobs?page_size={size}"
            if token:
                url += f"&page_token={token}"
            resp = http("GET", url, TOKEN)
            self.assertEqual(resp.status, 200, resp.body)
            page = resp.json()
            self.assertEqual(set(page), {"jobs", "next_page_token"}, page)
            out.append([j["id"] for j in page["jobs"]])
            token = page["next_page_token"]
            self.assertIsInstance(token, str)
            if not token:
                return out
        self.fail("more than 100 pages")

    def test_pages(self):
        ids = [self.create().json()["id"] for _ in range(6)]
        http("POST", f"{BASE}/v2/jobs/{ids[1]}/cancel", TOKEN)
        self.assertEqual(self.pages(2), [ids[0:2], ids[2:4], ids[4:6]])
        self.assertEqual(self.pages(3), [ids[0:3], ids[3:6]])
        self.assertEqual(self.pages(4), [ids[0:4], ids[4:6]])
        self.assertEqual(self.pages(6), [ids])
        self.assertEqual(self.pages(200), [ids])
        listed = http("GET", BASE + "/v2/jobs", TOKEN).json()["jobs"]
        self.assertEqual(listed[1]["state"], "cancelled")

        # The token stays valid while new jobs come.
        first = http("GET", BASE + "/v2/jobs?page_size=4", TOKEN).json()
        ids.append(self.create().json()["id"])
        second = http("GET", f"{BASE}/v2/jobs?page_size=4&page_token={first['next_page_token']}", TOKEN).json()
        self.assertEqual([j["id"] for j in second["jobs"]], ids[4:7])
        self.assertEqual(second["next_page_token"], "")

        for _ in range(60 - len(ids)):
            ids.append(self.create().json()["id"])
        page = http("GET", BASE + "/v2/jobs", TOKEN).json()
        self.assertEqual([j["id"] for j in page["jobs"]], ids[:50])
        rest = http("GET", f"{BASE}/v2/jobs?page_token={page['next_page_token']}", TOKEN).json()
        self.assertEqual([j["id"] for j in rest["jobs"]], ids[50:])
        self.assertEqual(rest["next_page_token"], "")

    def test_bad_parameters(self):
        for query in ["page_size=0", "page_size=201", "page_size=-1", "page_size=abc", "page_size=2.5",
                      "page_token=not-a-token-of-this-server"]:
            self.assertError(http("GET", f"{BASE}/v2/jobs?{query}", TOKEN), 400, "invalid_argument")


class ErrorsTest(ServerCase):
    """Rules 8 and 11 with JOBQ_QUEUE_LIMIT=2."""

    extra = {"JOBQ_QUEUE_LIMIT": "2"}

    def test_queue_limit(self):
        a = self.create().json()
        self.create()
        self.assertError(self.create(), 429, "resource_exhausted")
        http("POST", f"{BASE}/v2/jobs/{a['id']}/cancel", TOKEN)
        self.assertEqual(self.create().status, 201)

    def test_not_found(self):
        self.assertError(http("GET", BASE + "/v2/jobs/j-does-not-exist", TOKEN), 404, "not_found")
        self.assertError(http("POST", BASE + "/v2/jobs/j-does-not-exist/cancel", TOKEN), 404, "not_found")


class DrainTest(unittest.TestCase):
    """Rule 5 with JOBQ_DRAIN_DELAY=3s."""

    def test_drain(self):
        server = start({"JOBQ_DRAIN_DELAY": "3s"})
        try:
            server.wait_http(API)
            self.assertEqual(http("GET", BASE + "/readyz").status, 200)
            sent = time.monotonic()
            server.proc.send_signal(signal.SIGTERM)
            time.sleep(0.5)
            self.assertEqual(http("GET", BASE + "/readyz").status, 503)
            self.assertEqual(http("GET", BASE + "/livez").status, 200)
            self.assertEqual(http("POST", BASE + "/v2/jobs", TOKEN,
                                  {"command": ["true"], "timeout": "5s"}).status, 201)
            self.assertEqual(http("GET", f"http://127.0.0.1:{METRICS}/metrics").status, 200)
            time.sleep(1.5)
            self.assertIsNone(server.proc.poll(), "the server stopped before the drain delay")
            self.assertEqual(http("GET", BASE + "/readyz").status, 503)
            code = server.proc.wait(10)
            elapsed = time.monotonic() - sent
            self.assertEqual(code, 0, server.output())
            self.assertGreaterEqual(elapsed, 2.8)
            self.assertLess(elapsed, 9.0)
        finally:
            server.stop()

    def test_zero_drain(self):
        server = start({"JOBQ_DRAIN_DELAY": "0s"})
        try:
            server.wait_http(API)
            server.proc.send_signal(signal.SIGTERM)
            self.assertEqual(server.proc.wait(5), 0, server.output())
        finally:
            server.stop()


class MetricsTest(ServerCase):
    """Rule 3: the metrics listener."""

    def created_total(self):
        resp = http("GET", f"http://127.0.0.1:{METRICS}/metrics")
        self.assertEqual(resp.status, 200)
        m = re.search(r"^jobq_jobs_created_total(?:\{[^}]*\})? (\S+)$", resp.body, re.M)
        self.assertIsNotNone(m, resp.body)
        return float(m.group(1))

    def test_metrics(self):
        before = self.created_total()
        self.create()
        self.create()
        self.assertEqual(self.created_total(), before + 2)
        body = http("GET", f"http://127.0.0.1:{METRICS}/metrics").body
        for name in ["jobq_jobs_cancelled_total", "jobq_http_requests_total", "jobq_jobs_queued"]:
            self.assertIn(name, body)
        self.assertEqual(http("GET", BASE + "/metrics").status, 404)


if __name__ == "__main__":
    unittest.main()
