"""Tests of the client against a small fake server (contract version 2)."""

import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jobq_client import (
    Client,
    ConflictError,
    InvalidArgumentError,
    JobqError,
    NotFoundError,
    QueueFullError,
    UnauthenticatedError,
)
from jobq_client.cli import main
from jobq_client.durations import format_duration, parse_duration

TOKEN = "tok"


class FakeServer:
    """In-memory version 2 server. requests records (method, path, body)."""

    def __init__(self, limit=10):
        self.jobs = []
        self.limit = limit
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _error(self, status, code):
                self._send(status, {"error": {"code": code, "message": code.replace("_", " ")}})

            def _start(self, method):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n)) if n else None
                fake.requests.append((method, self.path, body))
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    self._error(401, "unauthenticated")
                    return None
                return body if body is not None else {}

            def do_POST(self):
                body = self._start("POST")
                if body is None:
                    return
                if self.path.endswith("/cancel"):
                    job = fake.find(self.path[len("/v2/jobs/"):-len("/cancel")])
                    if job is None:
                        return self._error(404, "not_found")
                    if job["state"] != "queued":
                        return self._error(409, "failed_precondition")
                    job["state"] = "cancelled"
                    return self._send(200, job)
                if sum(j["state"] == "queued" for j in fake.jobs) >= fake.limit:
                    return self._error(429, "resource_exhausted")
                if not body.get("command") or not isinstance(body.get("timeout"), str):
                    return self._error(400, "invalid_argument")
                job = {"id": f"j-{len(fake.jobs) + 1:04x}", "command": body["command"],
                       "timeout": format_duration(parse_duration(body["timeout"])), "state": "queued",
                       "created_at": "2026-11-19T10:00:00.123456789Z"}
                fake.jobs.append(job)
                self._send(201, job)

            def do_GET(self):
                if self._start("GET") is None:
                    return
                url = urllib.parse.urlsplit(self.path)
                if url.path == "/v2/jobs":
                    q = dict(urllib.parse.parse_qsl(url.query))
                    size = int(q.get("page_size", 50))
                    start = int(q.get("page_token") or 0)
                    page = fake.jobs[start:start + size]
                    more = start + size < len(fake.jobs)
                    return self._send(200, {"jobs": page, "next_page_token": str(start + size) if more else ""})
                job = fake.find(url.path[len("/v2/jobs/"):])
                if job is None:
                    return self._error(404, "not_found")
                self._send(200, job)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def find(self, job_id):
        return next((job for job in self.jobs if job["id"] == job_id), None)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


class DurationTest(unittest.TestCase):
    def test_format(self):
        cases = {
            timedelta(seconds=90): "1m30s",
            timedelta(hours=1): "1h0m0s",
            timedelta(milliseconds=1500): "1.5s",
            timedelta(microseconds=250): "250µs",
            timedelta(microseconds=1500): "1.5ms",
            timedelta(hours=2, minutes=45, milliseconds=500): "2h45m0.5s",
            timedelta(0): "0s",
        }
        for td, text in cases.items():
            self.assertEqual(format_duration(td), text)
            self.assertEqual(parse_duration(text), td)

    def test_parse(self):
        self.assertEqual(parse_duration("250us"), timedelta(microseconds=250))
        self.assertEqual(parse_duration("1.5h"), timedelta(minutes=90))
        self.assertEqual(parse_duration("-2s"), timedelta(seconds=-2))
        for bad in ["", "5", "1x", "s"]:
            with self.assertRaises(ValueError):
                parse_duration(bad)


class ClientTest(unittest.TestCase):
    def test_create_get_list_cancel(self):
        with FakeServer() as fake:
            c = Client(fake.url + "/", TOKEN)
            job = c.create_job(["echo", "hi"], timedelta(seconds=90))
            self.assertEqual(job.id, "j-0001")
            self.assertEqual(job.timeout, timedelta(seconds=90))
            self.assertEqual(job.created_at.microsecond, 123456)
            self.assertEqual(fake.requests[0], ("POST", "/v2/jobs", {"command": ["echo", "hi"], "timeout": "1m30s"}))
            self.assertEqual(c.get_job(job.id).command, ["echo", "hi"])
            for _ in range(4):
                c.create_job(["true"], timedelta(seconds=5))
            self.assertEqual([j.id for j in c.list_jobs(page_size=2)], [f"j-{i:04x}" for i in range(1, 6)])
            self.assertEqual(c.cancel_job("j-0002").state, "cancelled")

    def test_errors(self):
        with FakeServer(limit=1) as fake:
            c = Client(fake.url, TOKEN)
            with self.assertRaises(InvalidArgumentError):
                c.create_job(["true"], timedelta(0))
            c.create_job(["true"], timedelta(seconds=5))
            with self.assertRaises(QueueFullError) as ctx:
                c.create_job(["true"], timedelta(seconds=5))
            self.assertEqual((ctx.exception.code, ctx.exception.status), ("resource_exhausted", 429))
            with self.assertRaises(NotFoundError):
                c.get_job("j-9999")
            c.cancel_job("j-0001")
            with self.assertRaises(ConflictError):
                c.cancel_job("j-0001")
            with self.assertRaises(UnauthenticatedError):
                Client(fake.url, "wrong").get_job("j-0001")

    def test_unavailable(self):
        with FakeServer() as fake:
            url = fake.url
        with self.assertRaises(JobqError) as ctx:
            Client(url, TOKEN).get_job("j-0001")
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("unavailable", 0))


class CliTest(unittest.TestCase):
    def setUp(self):
        fd, self.token_file = tempfile.mkstemp()
        os.write(fd, f"{TOKEN}\n".encode())
        os.close(fd)
        self.addCleanup(os.unlink, self.token_file)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_submit_and_list(self):
        with FakeServer() as fake:
            base = ["--url", fake.url, "--token-file", self.token_file]
            code, out, _ = self.run_cli(*base, "submit", "--timeout", "90s", "--", "echo", "a b")
            self.assertEqual((code, out), (0, "j-0001\n"))
            code, out, _ = self.run_cli(*base, "list", "--page-size", "1")
            self.assertEqual((code, out), (0, "j-0001\tqueued\t1m30s\techo a b\n"))

    def test_errors(self):
        with FakeServer() as fake:
            code, out, err = self.run_cli("--url", fake.url, "--token-file", self.token_file, "get", "j-0005")
            self.assertEqual((code, out), (1, ""))
            self.assertTrue(err.startswith("error: not_found: "), err)


if __name__ == "__main__":
    unittest.main()
