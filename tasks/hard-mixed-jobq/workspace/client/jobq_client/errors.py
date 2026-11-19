"""Exceptions of the jobq client (contract v1)."""


class JobqError(Exception):
    """An error response of the server, or a failed request.

    status is the HTTP status (0 when no response came), message is the text
    of the response.
    """

    def __init__(self, status, message):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message


class InvalidRequestError(JobqError):
    """HTTP 400: the server did not accept the request."""


class NotFoundError(JobqError):
    """HTTP 404: the job does not exist."""


class ConflictError(JobqError):
    """HTTP 409: the job is not in a state that permits the operation."""


class QueueFullError(JobqError):
    """HTTP 429: the queue has the maximum number of queued jobs."""


_BY_STATUS = {
    400: InvalidRequestError,
    404: NotFoundError,
    409: ConflictError,
    429: QueueFullError,
}


def error_for(status, message):
    """Return the exception for an error response."""
    return _BY_STATUS.get(status, JobqError)(status, message)
