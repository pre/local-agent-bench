"""Request IDs of applied commands.

A client can send a command again with the same request ID, for example after
a timeout. The service then answers "duplicate" and does not apply it again.
The log keeps the IDs of the last `window` applied commands. Rejected and
ignored commands are not in the log, so a client can send them again.
"""

from collections import OrderedDict
from typing import Iterable


class RequestLog:
    def __init__(self, window: int):
        self.window = window
        self._ids: OrderedDict[str, None] = OrderedDict()

    def __contains__(self, rid: str) -> bool:
        return rid in self._ids

    def __len__(self) -> int:
        return len(self._ids)

    def add(self, rid: str) -> None:
        if rid in self._ids:
            return
        self._ids[rid] = None
        while len(self._ids) > self.window:
            self._ids.popitem(last=False)

    def ids(self) -> list[str]:
        """The IDs from the oldest to the newest."""
        return list(self._ids)

    @classmethod
    def from_ids(cls, window: int, ids: Iterable[str]) -> "RequestLog":
        log = cls(window)
        for rid in ids:
            log.add(rid)
        return log
