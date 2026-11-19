"""Tests of the client against a small fake server (contract v1)."""

import contextlib
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jobq_client import Client, ConflictError, InvalidRequestError, NotFoundError, QueueFullError
from jobq_client.cli import main


class FakeServer:
    """In-memory v1 server. requests records (method, path, body)."""

    def __init__(self, limit=10):
        self.jobs = []
        self.limit = limit
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, body):
                data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json" if not isinstance(body, str) else "text/plain")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n)) if n else None

            def do_POST(self):
                body = self._body()
                fake.requests.append(("POST", self.path, body))
                if self.path != "/v1/jobs":
                    return self._send(404, "not found\n")
                if sum(j["state"] == "queued" for j in fake.jobs) >= fake.limit:
                    return self._send(429, "queue is full\n")
                if not body.get("command") or not isinstance(body.get("timeout_seconds"), int):
                    return self._send(400, "bad request\n")
                job = {"id": len(fake.jobs) + 1, "command": body["command"],
                       "timeout_seconds": body["timeout_seconds"], "state": "queued",
                       "created_at": "2026-11-19T10:00:00.123456789Z"}
                fake.jobs.append(job)
                self._send(201, job)

            def do_GET(self):
                fake.requests.append(("GET", self.path, None))
                if self.path == "/v1/jobs":
                    return self._send(200, fake.jobs)
                job = fake.find(self.path)
                if job is None:
                    return self._send(404, "job not found\n")
                self._send(200, job)

            def do_DELETE(self):
                fake.requests.append(("DELETE", self.path, None))
                job = fake.find(self.path)
                if job is None:
                    return self._send(404, "job not found\n")
                if job["state"] != "queued":
                    return self._send(409, "job is not queued\n")
                job["state"] = "cancelled"
                self._send(200, job)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def find(self, path):
        prefix = "/v1/jobs/"
        if not path.startswith(prefix):
            return None
        for job in self.jobs:
            if str(job["id"]) == path[len(prefix):]:
                return job
        return None

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


class ClientTest(unittest.TestCase):
    def test_create_get_list_cancel(self):
        with FakeServer() as fake:
            c = Client(fake.url + "/")
            job = c.create_job(["echo", "hi"], 90)
            self.assertEqual(job.id, 1)
            self.assertEqual(job.timeout_seconds, 90)
            self.assertEqual(job.created_at.microsecond, 123456)
            self.assertEqual(fake.requests[0], ("POST", "/v1/jobs", {"command": ["echo", "hi"], "timeout_seconds": 90}))
            self.assertEqual(c.get_job(1).command, ["echo", "hi"])
            c.create_job(["true"], 5)
            self.assertEqual([j.id for j in c.list_jobs()], [1, 2])
            self.assertEqual(c.cancel_job(2).state, "cancelled")

    def test_errors(self):
        with FakeServer(limit=1) as fake:
            c = Client(fake.url)
            with self.assertRaises(InvalidRequestError):
                c.create_job([], 5)
            c.create_job(["true"], 5)
            with self.assertRaises(QueueFullError) as ctx:
                c.create_job(["true"], 5)
            self.assertEqual(ctx.exception.status, 429)
            with self.assertRaises(NotFoundError):
                c.get_job(7)
            c.cancel_job(1)
            with self.assertRaises(ConflictError):
                c.cancel_job(1)


class CliTest(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_submit_and_list(self):
        with FakeServer() as fake:
            code, out, _ = self.run_cli("--url", fake.url, "submit", "--timeout-seconds", "30", "--", "echo", "a b")
            self.assertEqual((code, out), (0, "1\n"))
            code, out, _ = self.run_cli("--url", fake.url, "list")
            self.assertEqual((code, out), (0, "1\tqueued\t30s\techo a b\n"))

    def test_not_found(self):
        with FakeServer() as fake:
            code, out, err = self.run_cli("--url", fake.url, "get", "5")
            self.assertEqual((code, out), (1, ""))
            self.assertIn("error:", err)


if __name__ == "__main__":
    unittest.main()
