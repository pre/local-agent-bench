"""HTTP client of the jobq API (contract v1)."""

import json
import urllib.error
import urllib.request

from .errors import JobqError, error_for
from .models import Job


class Client:
    """Client of one jobq server.

    base_url is the root URL of the service, for example
    http://jobq.jobs.svc.cluster.local. The client adds the API path.
    """

    def __init__(self, base_url, timeout=10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def create_job(self, command, timeout_seconds):
        """Create a queued job and return it."""
        body = {"command": list(command), "timeout_seconds": int(timeout_seconds)}
        return Job.from_dict(self._request("POST", "/v1/jobs", body))

    def get_job(self, job_id):
        return Job.from_dict(self._request("GET", f"/v1/jobs/{int(job_id)}"))

    def list_jobs(self):
        """Return all jobs, the oldest first."""
        return [Job.from_dict(item) for item in self._request("GET", "/v1/jobs")]

    def cancel_job(self, job_id):
        return Job.from_dict(self._request("DELETE", f"/v1/jobs/{int(job_id)}"))

    def _request(self, method, path, body=None):
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace").strip()
            raise error_for(e.code, text) from None
        except urllib.error.URLError as e:
            raise JobqError(0, str(e.reason)) from None
