"""Hidden tests of the Python client and its command line (contract version 2,
rules 12 to 14), against the real server and against a fake server."""

import json
import os
import subprocess
import sys
import threading
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jobqcheck import WORK, http, write_token_file
from test_server import start

sys.path.insert(0, os.path.join(WORK, "client"))

import jobq_client  # noqa: E402
from jobq_client import errors as jobq_errors  # noqa: E402

TOKEN = "srv-Token_7f3a9c"
API = 17070
BASE = f"http://127.0.0.1:{API}"


class LiveCase(unittest.TestCase):
    extra = {"JOBQ_MAX_TIMEOUT": "6h"}

    @classmethod
    def setUpClass(cls):
        cls.server = start(cls.extra)
        try:
            cls.server.wait_http(API)
        except AssertionError:
            cls.server.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        os.unlink(cls.server.token_path)

    def client(self, token=TOKEN, slash=False):
        return jobq_client.Client(BASE + ("/" if slash else ""), token)


class ClientApiTest(LiveCase):
    """Rule 12 against the real server."""

    def test_create_get_cancel(self):
        c = self.client(slash=True)
        job = c.create_job(["echo", "a b"], timedelta(minutes=1, seconds=30))
        self.assertIsInstance(job, jobq_client.Job)
        self.assertIsInstance(job.id, str)
        self.assertEqual(job.command, ["echo", "a b"])
        self.assertEqual(job.timeout, timedelta(seconds=90))
        self.assertEqual(job.state, "queued")
        self.assertIsInstance(job.created_at, datetime)
        self.assertIsNotNone(job.created_at.tzinfo)
        self.assertLess(abs(job.created_at - datetime.now(timezone.utc)), timedelta(minutes=5))

        got = self.client().get_job(job.id)
        self.assertEqual((got.id, got.command, got.timeout, got.state), (job.id, job.command, job.timeout, "queued"))
        self.assertEqual(c.cancel_job(job.id).state, "cancelled")
        self.assertEqual(c.get_job(job.id).state, "cancelled")
        with self.assertRaises(jobq_client.ConflictError) as ctx:
            c.cancel_job(job.id)
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("failed_precondition", 409))

    def test_timeout_round_trip(self):
        c = self.client()
        for td in [
            timedelta(hours=1),
            timedelta(seconds=1, milliseconds=500),
            timedelta(microseconds=250),
            timedelta(microseconds=1500),
            timedelta(hours=2, minutes=45, milliseconds=500),
            timedelta(microseconds=1_500_250),
            timedelta(hours=5, minutes=59, seconds=59, microseconds=999_999),
            timedelta(hours=6),
            timedelta(seconds=59, microseconds=1),
        ]:
            job = c.create_job(["true"], td)
            self.assertEqual(job.timeout, td, td)
            self.assertEqual(c.get_job(job.id).timeout, td, td)
        # The server stores the value that the client sent: check its text.
        raw = http("GET", f"{BASE}/v2/jobs/{job.id}", TOKEN).json()
        self.assertEqual(raw["timeout"], "59.000001s")

    def test_invalid_timeout(self):
        c = self.client()
        for td in [timedelta(0), timedelta(seconds=-1), timedelta(microseconds=-1)]:
            with self.assertRaises(jobq_client.InvalidArgumentError):
                c.create_job(["true"], td)
        with self.assertRaises(jobq_client.InvalidArgumentError) as ctx:
            c.create_job(["true"], timedelta(hours=6, microseconds=1))
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("invalid_argument", 400))

    def test_errors_of_the_server(self):
        with self.assertRaises(jobq_client.NotFoundError) as ctx:
            self.client().get_job("j-does-not-exist")
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("not_found", 404))
        self.assertIsInstance(ctx.exception.message, str)
        with self.assertRaises(jobq_client.UnauthenticatedError) as ctx:
            self.client(token="wrong").get_job("j-1")
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("unauthenticated", 401))


class ClientPagesTest(LiveCase):
    """Rule 12: list_jobs over all pages, against the real server."""

    def test_list_all_pages(self):
        c = self.client()
        ids = [c.create_job(["true"], timedelta(seconds=5)).id for _ in range(7)]
        c.cancel_job(ids[2])
        result = c.list_jobs(page_size=3)
        self.assertTrue(hasattr(result, "__next__"), "list_jobs does not return an iterator")
        jobs = list(result)
        self.assertEqual([j.id for j in jobs], ids)
        self.assertEqual(jobs[2].state, "cancelled")
        self.assertEqual([j.id for j in c.list_jobs(page_size=1)], ids)
        self.assertEqual([j.id for j in c.list_jobs(page_size=7)], ids)
        for _ in range(113):
            ids.append(c.create_job(["true"], timedelta(seconds=5)).id)
        self.assertEqual([j.id for j in c.list_jobs()], ids)


class FakeServer:
    """Records the requests and answers each request with a fixed response,
    or with pages of five jobs for GET /v2/jobs."""

    def __init__(self, status=200, body="", content_type="application/json"):
        self.requests = []
        fake = self
        job = {"command": ["true"], "timeout": "5s", "state": "queued",
               "created_at": "2026-11-19T10:00:00Z"}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_any(self):
                n = int(self.headers.get("Content-Length") or 0)
                fake.requests.append((self.command, self.path, self.headers.get("Authorization"),
                                      self.rfile.read(n).decode() if n else ""))
                url = urllib.parse.urlsplit(self.path)
                if status == 200 and url.path == "/v2/jobs":
                    q = dict(urllib.parse.parse_qsl(url.query))
                    size = int(q.get("page_size", 2))
                    start = int(q.get("page_token", "0").lstrip("t") or 0)
                    ids = [f"f{i}" for i in range(5)][start:start + size]
                    nxt = f"t{start + size}" if start + size < 5 else ""
                    data = json.dumps({"jobs": [dict(job, id=i) for i in ids], "next_page_token": nxt})
                else:
                    data = body
                raw = data.encode()
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            do_GET = do_POST = do_DELETE = do_PUT = handle_any

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def error_body(code):
    return json.dumps({"error": {"code": code, "message": f"text of {code}"}})


class ClientErrorsTest(unittest.TestCase):
    """Rule 13, and the requests of rule 12, against a fake server."""

    def test_classes(self):
        for name in ["JobqError", "InvalidArgumentError", "UnauthenticatedError", "NotFoundError",
                     "ConflictError", "QueueFullError"]:
            cls = getattr(jobq_errors, name)
            self.assertIs(getattr(jobq_client, name), cls)
            self.assertTrue(issubclass(cls, jobq_errors.JobqError))

    def test_code_mapping(self):
        cases = [
            (400, "invalid_argument", jobq_client.InvalidArgumentError),
            (401, "unauthenticated", jobq_client.UnauthenticatedError),
            (404, "not_found", jobq_client.NotFoundError),
            (409, "failed_precondition", jobq_client.ConflictError),
            (429, "resource_exhausted", jobq_client.QueueFullError),
            (500, "internal", jobq_client.JobqError),
            (418, "teapot_mode", jobq_client.JobqError),
        ]
        for status, code, cls in cases:
            with FakeServer(status, error_body(code)) as fake:
                with self.assertRaises(jobq_client.JobqError) as ctx:
                    jobq_client.Client(fake.url, "tok").get_job("j-1")
            e = ctx.exception
            self.assertIs(type(e), cls, code)
            self.assertEqual((e.code, e.status, e.message), (code, status, f"text of {code}"))

    def test_unknown_body(self):
        page = "<html><body>502 Bad Gateway</body></html>"
        with FakeServer(502, page, "text/html") as fake:
            with self.assertRaises(jobq_client.JobqError) as ctx:
                jobq_client.Client(fake.url, "tok").get_job("j-1")
        self.assertIs(type(ctx.exception), jobq_client.JobqError)
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("unknown", 502))
        self.assertIn("502 Bad Gateway", ctx.exception.message)

    def test_unavailable(self):
        with FakeServer() as fake:
            url = fake.url
        with self.assertRaises(jobq_client.JobqError) as ctx:
            jobq_client.Client(url, "tok").get_job("j-1")
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("unavailable", 0))

    def test_requests(self):
        with FakeServer() as fake:
            c = jobq_client.Client(fake.url + "/", "tok-1")
            self.assertEqual([j.id for j in c.list_jobs()], [f"f{i}" for i in range(5)])
            self.assertEqual([j.id for j in c.list_jobs(page_size=4)], [f"f{i}" for i in range(5)])
        paths = [urllib.parse.urlsplit(r[1]) for r in fake.requests]
        self.assertTrue(all(r[2] == "Bearer tok-1" for r in fake.requests), fake.requests)
        self.assertTrue(all(p.path == "/v2/jobs" for p in paths), paths)
        queries = [dict(urllib.parse.parse_qsl(p.query)) for p in paths]
        self.assertEqual(len(queries), 5, queries)
        # page_size=None sends no page_size. Each request after the first sends the last token.
        self.assertEqual(queries[:3], [{}, {"page_token": "t2"}, {"page_token": "t4"}])
        self.assertEqual(queries[3], {"page_size": "4"})
        self.assertEqual(queries[4].get("page_token"), "t4")


class CliTest(LiveCase):
    """Rule 14 against the real server."""

    def run_cli(self, *argv, env=None, token_file=None):
        full_env = {"PATH": os.environ["PATH"], "PYTHONPATH": os.path.join(WORK, "client"),
                    "PYTHONDONTWRITEBYTECODE": "1"}
        full_env.update(env or {})
        args = [sys.executable, "-m", "jobq_client"]
        if token_file:
            args += ["--url", BASE, "--token-file", token_file]
        proc = subprocess.run([*args, *argv], env=full_env, capture_output=True, text=True, timeout=30,
                              cwd="/tmp")
        return proc.returncode, proc.stdout, proc.stderr

    def test_cli(self):
        tf = self.server.token_path
        code, out, err = self.run_cli("submit", "--timeout", "1m30s", "--", "echo", "a b", token_file=tf)
        self.assertEqual(code, 0, err)
        first = out.strip()
        self.assertEqual(out, first + "\n")
        code, out, err = self.run_cli("submit", "--timeout", "1500ms", "--", "sleep", "1",
                                      env={"JOBQ_URL": BASE, "JOBQ_TOKEN_FILE": tf})
        self.assertEqual(code, 0, err)
        second = out.strip()

        code, out, err = self.run_cli("list", token_file=tf)
        self.assertEqual(code, 0, err)
        self.assertEqual(out, f"{first}\tqueued\t1m30s\techo a b\n{second}\tqueued\t1.5s\tsleep 1\n")
        code, out, err = self.run_cli("list", "--page-size", "1", token_file=tf)
        self.assertEqual((code, len(out.splitlines())), (0, 2), err)

        code, out, err = self.run_cli("get", second, token_file=tf)
        self.assertEqual((code, out), (0, f"{second}\tqueued\t1.5s\tsleep 1\n"), err)
        code, out, err = self.run_cli("cancel", first, token_file=tf)
        self.assertEqual((code, out), (0, f"{first}\tcancelled\t1m30s\techo a b\n"), err)

        code, out, err = self.run_cli("submit", "--timeout", "250us", "--", "true", token_file=tf)
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli("get", out.strip(), token_file=tf)
        self.assertEqual(out.split("\t")[2], "250µs")

    def test_cli_errors(self):
        tf = self.server.token_path
        code, out, err = self.run_cli("get", "j-does-not-exist", token_file=tf)
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("error: not_found: "), err)
        code, out, err = self.run_cli("cancel", "j-does-not-exist", token_file=tf)
        self.assertEqual(code, 1)
        code, out, err = self.run_cli("list", env={"JOBQ_URL": BASE})
        self.assertEqual((code, out), (2, ""))
        self.assertNotEqual(err, "")
        wrong = write_token_file("wrong\n")
        try:
            code, out, err = self.run_cli("list", token_file=wrong)
        finally:
            os.unlink(wrong)
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("error: unauthenticated: "), err)


if __name__ == "__main__":
    unittest.main()
