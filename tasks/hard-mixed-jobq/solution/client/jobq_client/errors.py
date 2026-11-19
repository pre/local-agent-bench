"""Exceptions of the jobq client (contract version 2, rule 13)."""


class JobqError(Exception):
    """An error response of the server, or a failed request.

    code is the error code of the server, "unknown" for an error response
    without a version 2 error body, or "unavailable" when no response came.
    status is the HTTP status (0 when no response came).
    """

    def __init__(self, code, message, status=0):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status = status


class InvalidArgumentError(JobqError):
    """invalid_argument: the server did not accept the request."""


class UnauthenticatedError(JobqError):
    """unauthenticated: the token is missing or wrong."""


class NotFoundError(JobqError):
    """not_found: the job does not exist."""


class ConflictError(JobqError):
    """failed_precondition: the job is not in a state that permits the operation."""


class QueueFullError(JobqError):
    """resource_exhausted: the queue has the maximum number of queued jobs."""


_BY_CODE = {
    "invalid_argument": InvalidArgumentError,
    "unauthenticated": UnauthenticatedError,
    "not_found": NotFoundError,
    "failed_precondition": ConflictError,
    "resource_exhausted": QueueFullError,
}


def error_for(code, message, status):
    """Return the exception for an error code."""
    return _BY_CODE.get(code, JobqError)(code, message, status)
