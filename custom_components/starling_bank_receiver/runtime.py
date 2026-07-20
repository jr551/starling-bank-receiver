"""Runtime state for a Starling Bank Receiver config entry."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from .models import FeedItem


class ReceiverData:
    """Coordinate entities and deduplicate callback deliveries."""

    def __init__(self, secret: str, public_key_pem: str | None) -> None:
        self.secret = secret
        self.public_key = (
            load_pem_public_key(public_key_pem.encode()) if public_key_pem else None
        )
        self.latest: FeedItem | None = None
        self.total_received = 0
        self.total_duplicates = 0
        self.total_rejected = 0
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

    def signature_is_valid(self, body: bytes, signature: str | None) -> bool:
        """Validate Starling V2's SHA512withRSA signature over raw JSON bytes."""
        if self.public_key is None or not signature:
            self.total_rejected += 1
            return False
        try:
            self.public_key.verify(
                base64.b64decode(signature, validate=True),
                body,
                padding.PKCS1v15(),
                hashes.SHA512(),
            )
        except (InvalidSignature, ValueError):
            self.total_rejected += 1
            return False
        return True
