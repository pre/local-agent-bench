"""HTTP client of the jobq API (contract version 2)."""

import json
import urllib.error
import urllib.parse
import urllib.request

from .durations import format_duration, to_nanoseconds
from .errors import InvalidArgumentError, JobqError, error_for
from .models import Job


class Client:
    """Client of one jobq server.

    base_url is the root URL of the service, for example http://jobq.jobs.svc.
    The client adds the API path and the bearer token.
    """

    def __init__(self, base_url, token, timeout=10.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def create_job(self, command, timeout):
        """Create a queued job. timeout is a datetime.timedelta."""
        if to_nanoseconds(timeout) <= 0:
            raise InvalidArgumentError("invalid_argument", "timeout must be more than 0")
        body = {"command": list(command), "timeout": format_duration(timeout)}
        return Job.from_dict(self._request("POST", "/v2/jobs", body))

    def get_job(self, job_id):
        return Job.from_dict(self._request("GET", "/v2/jobs/" + _quote(job_id)))

    def cancel_job(self, job_id):
        return Job.from_dict(self._request("POST", "/v2/jobs/" + _quote(job_id) + "/cancel", {}))

    def list_jobs(self, page_size=None):
        """Iterate over all jobs, the oldest first. Requests one page at a time."""
        token = ""
        while True:
            query = {}
            if page_size is not None:
                query["page_size"] = str(page_size)
            if token:
                query["page_token"] = token
            path = "/v2/jobs"
            if query:
                path += "?" + urllib.parse.urlencode(query)
            page = self._request("GET", path)
            for item in page["jobs"]:
                yield Job.from_dict(item)
            token = page.get("next_page_token") or ""
            if not token:
                return

    def _request(self, method, path, body=None):
        data = None
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            with e:
                text = e.read().decode(errors="replace")
            raise _error_from_response(e.code, text) from None
        except (urllib.error.URLError, OSError) as e:
            raise JobqError("unavailable", str(getattr(e, "reason", e)), 0) from None


def _quote(job_id):
    return urllib.parse.quote(str(job_id), safe="")


def _error_from_response(status, text):
    try:
        detail = json.loads(text)["error"]
        code, message = detail["code"], detail["message"]
        if isinstance(code, str) and isinstance(message, str):
            return error_for(code, message, status)
    except (ValueError, KeyError, TypeError):
        pass
    return JobqError("unknown", text.strip(), status)
