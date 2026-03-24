from __future__ import annotations

from collections import deque


class EventBridge:
    def __init__(self, maxlen: int = 500):
        self._queue: deque[tuple[str, dict]] = deque(maxlen=maxlen)

    def push(self, event_type: str, data: dict) -> None:
        self._queue.append((event_type, data))

    async def async_push(self, event_type: str, data: dict) -> None:
        self._queue.append((event_type, data))

    def drain(self) -> list[tuple[str, dict]]:
        events = list(self._queue)
        self._queue.clear()
        return events
