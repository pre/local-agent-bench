# jobq contract

This document is the contract between the four parts of jobq:

| Part | Path |
|---|---|
| Server (Go) | `service/` |
| Python client and command line | `client/` |
| Deploy script | `deploy/deploy.sh`, `deploy/env/*.env` |
| Kubernetes manifests | `deploy/templates/*.yaml` |

Version 1 is the current contract. Version 2 is approved (decision record
below) and replaces version 1 completely. There is no transition period: the
server, the client and the manifests of version 2 do not support version 1.

## Version 1 (current)

- One HTTP listener on `JOBQ_PORT` (default 8080). It serves the API, `GET /healthz` and `GET /metrics`.
- `POST /v1/jobs` with `{"command": [...], "timeout_seconds": N}` creates a job. `GET /v1/jobs` returns a JSON array of all jobs. `GET /v1/jobs/{id}` returns one job. `DELETE /v1/jobs/{id}` cancels a job.
- A job is `{"id": 1, "command": [...], "timeout_seconds": 90, "state": "queued", "created_at": "<RFC 3339>"}`. The ID is an integer.
- Errors are plain text with the HTTP status.
- No authentication.
- Environment of the server: `JOBQ_PORT`, `JOBQ_MAX_TIMEOUT_SECONDS`, `JOBQ_QUEUE_LIMIT`.

## Decision record: version 2

Status: approved. Reasons: the platform team requires authentication and a
separate metrics port, the integer IDs leak the job count, and the list
response becomes too large in production.

## Version 2

The numbered rules are the contract. All parts must agree with each rule.

### Server process

1. **Environment.** The server reads these variables. An empty or unset variable gives the default.

   | Variable | Value | Default |
   |---|---|---|
   | `JOBQ_API_ADDR` | listen address of the API listener, for example `:7070` | `:7070` |
   | `JOBQ_METRICS_ADDR` | listen address of the metrics listener | `:9102` |
   | `JOBQ_TOKEN_FILE` | path of the file that contains the API token | none, required |
   | `JOBQ_MAX_TIMEOUT` | largest job timeout, a Go duration (rule 9) | `1h` |
   | `JOBQ_QUEUE_LIMIT` | largest number of queued jobs, an integer of 1 or more | `100` |
   | `JOBQ_DRAIN_DELAY` | drain time after SIGTERM, a Go duration of 0 or more (rule 5) | `5s` |

2. **Refused start.** The server writes a message to stderr and exits with status 2, before it listens, when:
   - `JOBQ_TOKEN_FILE` is not set, the file cannot be read, or the token (rule 6) is empty.
   - a value of rule 1 is not valid.
   - a version 1 variable is set to a value that is not empty: `JOBQ_PORT` or `JOBQ_MAX_TIMEOUT_SECONDS`. This prevents that an old manifest starts a version 2 server with wrong values.

3. **Two listeners.** The API listener (`JOBQ_API_ADDR`) serves the `/v2/` API and the probes of rule 4. The metrics listener (`JOBQ_METRICS_ADDR`) serves `GET /metrics` in the Prometheus text format with the same metric names as version 1 (`jobq_jobs_created_total`, `jobq_jobs_cancelled_total`, `jobq_http_requests_total`, `jobq_jobs_queued`). The API listener does not serve `/metrics` (404). The paths `/v1/...` and `/healthz` do not exist in version 2 (404).

4. **Probes.** On the API listener, without authentication:
   - `GET /livez` gives 200 while the process runs.
   - `GET /readyz` gives 200 when the server accepts work, and 503 during the drain (rule 5).

5. **Drain.** On SIGTERM the server immediately changes `/readyz` to 503. It continues to serve all other requests for `JOBQ_DRAIN_DELAY`. Then it stops both listeners gracefully and exits with status 0. Kubernetes must give the pod enough time: `terminationGracePeriodSeconds` of the Deployment must be at least the drain delay plus 10 seconds.

### API

6. **Authentication.** Each request to a path below `/v2/` must have the header `Authorization: Bearer <token>`. The token is the content of the file `JOBQ_TOKEN_FILE`, without leading and trailing white space (a Kubernetes Secret file often ends with a newline). The server reads the file once at the start. A missing or wrong token gives 401 with the error code `unauthenticated` (rule 11). The probes and `/metrics` do not need a token.

7. **Endpoints.** All bodies are JSON (`Content-Type: application/json`).

   | Method and path | Success |
   |---|---|
   | `POST /v2/jobs` | 201, the new job |
   | `GET /v2/jobs/{id}` | 200, the job |
   | `POST /v2/jobs/{id}/cancel` | 200, the cancelled job |
   | `GET /v2/jobs?page_size=N&page_token=T` | 200, a page (rule 10) |

   The request body of `POST /v2/jobs` is `{"command": ["echo", "hi"], "timeout": "1m30s"}`. Both fields are required. `command` is a list of 1 or more strings. A body that is not a JSON object with these fields, or that has other fields, gives `invalid_argument`. The body of `POST /v2/jobs/{id}/cancel` is empty or `{}`.

8. **Job.** A job is:

   ```json
   {"id": "j-4f9c2a7e1b3d5068", "command": ["echo", "hi"], "timeout": "1m30s",
    "state": "queued", "created_at": "2026-11-19T10:00:00.123456789Z"}
   ```

   - `id` is an opaque string of 1 to 64 characters from `[A-Za-z0-9_-]`. A client must not interpret it. Two jobs never have the same ID.
   - `state` is `queued` or `cancelled`. Only a queued job can be cancelled. A cancel of a job that is not queued gives `failed_precondition`.
   - `created_at` is an RFC 3339 time in UTC.
   - The queue limit counts the queued jobs. A create when `JOBQ_QUEUE_LIMIT` jobs are queued gives `resource_exhausted`.
   - An unknown ID gives `not_found`.

9. **Timeout.** `timeout` is a Go duration, as `time.ParseDuration` accepts it (for example `90s`, `1m30s`, `1.5s`, `250ms`, `250us`, `250µs`). It must be more than 0 and not more than `JOBQ_MAX_TIMEOUT`, else `invalid_argument`. In each response, `timeout` is the text of Go `time.Duration.String()` of the value, for example `90s` gives `1m30s`, `1h` gives `1h0m0s`, `1500ms` gives `1.5s`, `0.25ms` gives `250µs` (the micro sign U+00B5).

10. **Pages.** `GET /v2/jobs` returns `{"jobs": [...], "next_page_token": "..."}` with the jobs in the order of creation, the oldest first. Cancelled jobs are included.
    - `page_size` is an integer from 1 to 200. The default is 50. Another value gives `invalid_argument`.
    - Without `page_token` the page starts at the oldest job. With `page_token` the page starts after the last job of the page that gave the token.
    - `next_page_token` is an opaque string. It is the empty string when no job comes after this page, also when the page is exactly full. Thus a client never needs to request an empty page.
    - A `page_token` that the server did not give gives `invalid_argument`.

11. **Errors.** Each error response has the body `{"error": {"code": "<code>", "message": "<text>"}}` and the content type `application/json`. Codes and statuses:

    | Code | HTTP status |
    |---|---|
    | `invalid_argument` | 400 |
    | `unauthenticated` | 401 |
    | `not_found` | 404 |
    | `failed_precondition` | 409 |
    | `resource_exhausted` | 429 |
    | `internal` | 500 |

### Python client

12. **API.** The package `jobq_client` exports:
    - `Client(base_url, token, timeout=10.0)`: `base_url` is the root URL of the service (for example `http://jobq.jobs.svc`, with or without a trailing slash). The client adds `/v2/...` and the `Authorization` header with `token`.
    - `create_job(command, timeout)`: `timeout` is a `datetime.timedelta`. The client sends it as a Go duration with no loss of precision (microseconds included). A timedelta of 0 or less raises `InvalidArgumentError` (the client can raise it before it sends a request).
    - `get_job(job_id)` and `cancel_job(job_id)`: `job_id` is the string ID.
    - `list_jobs(page_size=None)`: returns an iterator over all jobs, the oldest first. It requests the pages one after the other and follows `next_page_token` until it is empty. `page_size=None` sends no `page_size`.
    - `Job` (a dataclass): `id` (str), `command` (list of str), `timeout` (`datetime.timedelta`, parsed from the response text of rule 9), `state` (str), `created_at` (timezone-aware `datetime`).

13. **Exceptions.** The module `jobq_client.errors` defines these classes, and `jobq_client` exports them. Each is a subclass of `JobqError`. `JobqError` has the attributes `code` (str), `message` (str) and `status` (int, 0 when no response came).

    | Error code | Class |
    |---|---|
    | `invalid_argument` | `InvalidArgumentError` (replaces `InvalidRequestError` of version 1) |
    | `unauthenticated` | `UnauthenticatedError` |
    | `not_found` | `NotFoundError` |
    | `failed_precondition` | `ConflictError` |
    | `resource_exhausted` | `QueueFullError` |
    | another code | `JobqError` with that code |

    When an error response does not have the body of rule 11 (for example an HTML page of a proxy), the client raises `JobqError` with the code `unknown`, the HTTP status and the body text as the message. When no response comes (for example connection refused), the client raises `JobqError` with the code `unavailable` and the status 0.

14. **Command line.** `python -m jobq_client [--url URL] [--token-file FILE] COMMAND`. `--url` defaults to `$JOBQ_URL`, then `http://127.0.0.1:7070`. `--token-file` defaults to `$JOBQ_TOKEN_FILE`. The token is the file content without leading and trailing white space. Without a token file the command line writes a message to stderr and exits with status 2.
    - `submit --timeout DURATION -- COMMAND...` creates a job and writes its ID and a newline to stdout. `DURATION` is a Go duration (rule 9).
    - `get ID`, `cancel ID` write one job line. `list [--page-size N]` writes one line for each job of all pages, the oldest first.
    - A job line is the ID, the state, the timeout and the command, separated by tabs. The timeout is in the text of rule 9 (for example `1m30s`). The command is its arguments separated by one space.
    - For an error the command line writes `error: <code>: <message>` to stderr and exits with status 1.

### Deployment

15. **Deploy script.** `deploy/deploy.sh --env NAME --token-file FILE [--render-only DIR]`. `--token-file` is required: without it, or when the file cannot be read or contains only white space, the script writes a message to stderr and exits with a status that is not 0. With `--render-only DIR` the script writes the rendered manifests (YAML, one or more files) to `DIR` and does not call kubectl. The rendered manifests include a Secret `jobq-api-token` with the key `token` whose value is the content of the token file. The token must not appear in other rendered files. `shellcheck` with the default settings reports nothing for `deploy/deploy.sh`.

16. **Values of the environments.**

    | Value | staging | production |
    |---|---|---|
    | Maximum timeout | `1h` | `6h` |
    | Queue limit | 500 | 2000 |
    | Drain delay | `5s` | `20s` |
    | Image tag | `2.0.0` | `2.0.0` |

17. **Ports.** The container `server` of the Deployment `jobq` has two named ports: `api` (7070) for the API listener and `metrics` (9102) for the metrics listener. The server must listen on these ports with the environment that the Deployment gives it.
    - The Service `jobq` has the port `http` (80) with the target port `api`.
    - The pod annotations `prometheus.io/port` and `prometheus.io/path` give the metrics port number and `/metrics`.
    - The readiness probe uses `GET /readyz` and the liveness probe uses `GET /livez`, both on the port `api`.
    - The NetworkPolicy `jobq` allows ingress only on the two container ports.

18. **Token in the pod.** The Secret `jobq-api-token` is mounted read-only as a volume, and `JOBQ_TOKEN_FILE` gives the path of the file of the key `token` in that volume. The token is not in an environment variable.

19. **Configuration in the pod.** The settings of rule 1 that change between the environments (maximum timeout, queue limit, drain delay) come from the ConfigMap `jobq-config`. The Deployment does not set the version 1 variables (rule 2).
