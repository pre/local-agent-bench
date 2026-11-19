"""Time source of the service.

Events carry a UTC time stamp. Tests and replays of incidents set
STOCKD_FIXED_TIME to an ISO time; each call of now() then advances it by one
second, so the files are the same in each run.
"""

import datetime as _dt
import os

_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class Clock:
    def now(self) -> str:
        return _dt.datetime.now(_dt.timezone.utc).strftime(_FORMAT)


class FixedClock(Clock):
    def __init__(self, start: str):
        self._t = _dt.datetime.strptime(start, _FORMAT).replace(tzinfo=_dt.timezone.utc)

    def now(self) -> str:
        value = self._t.strftime(_FORMAT)
        self._t += _dt.timedelta(seconds=1)
        return value


def default_clock() -> Clock:
    fixed = os.environ.get("STOCKD_FIXED_TIME")
    if fixed:
        return FixedClock(fixed)
    return Clock()
