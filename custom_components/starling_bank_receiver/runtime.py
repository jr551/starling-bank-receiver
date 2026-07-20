"""Runtime state for a Starling Bank Receiver config entry."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable

from .models import FeedItem


class ReceiverData:
    """Coordinate entities and deduplicate callback deliveries."""

    def __init__(self, secret: str) -> None:
        self.secret = secret
        self.latest: FeedItem | None = None
        self.total_received = 0
        self.total_duplicates = 0
        self._seen: deque[str] = deque(maxlen=256)
        self._listeners: list[Callable[[FeedItem], None]] = []

    def add_listener(self, listener: Callable[[FeedItem], None]) -> Callable[[], None]:
        """Register an entity update callback."""
        self._listeners.append(listener)

        def remove() -> None:
            self._listeners.remove(listener)

        return remove

    def accept(self, item: FeedItem) -> bool:
        """Remember a payload and update listeners; return false for a replay."""
        if item.event_uid in self._seen:
            self.total_duplicates += 1
            return False
        self._seen.append(item.event_uid)
        self.latest = item
        self.total_received += 1
        for listener in tuple(self._listeners):
            listener(item)
        return True
