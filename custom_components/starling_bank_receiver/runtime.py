"""Runtime state for a Starling Bank Receiver config entry."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .api import StarlingDataUpdateCoordinator
from .const import DOMAIN
from .models import FeedItem

STORAGE_VERSION = 1
MAX_STORED_ITEMS = 250


class ReceiverData:
    """Coordinate entities and deduplicate callback deliveries."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        secret: str,
        public_key_pem: str | None,
    ) -> None:
        self.hass = hass
        self.secret = secret
        self.public_key = (
            load_pem_public_key(public_key_pem.encode()) if public_key_pem else None
        )
        self.coordinator: StarlingDataUpdateCoordinator | None = None
        self.latest: FeedItem | None = None
        self.total_received = 0
        self.total_duplicates = 0
        self.total_rejected = 0
        self._seen: deque[str] = deque(maxlen=256)
        self._listeners: list[Callable[[FeedItem], None]] = []
        self._items: deque[FeedItem] = deque(maxlen=MAX_STORED_ITEMS)
        self._store = Store[dict[str, object]](
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )

    async def async_restore(self) -> None:
        """Restore callbacks from HA's integration-managed persistent storage."""
        saved = await self._store.async_load()
        if not isinstance(saved, dict):
            return
        self.total_received = int(saved.get("total_received", 0))
        self.total_duplicates = int(saved.get("total_duplicates", 0))
        self.total_rejected = int(saved.get("total_rejected", 0))
        for value in saved.get("items", []):
            if not isinstance(value, dict):
                continue
            try:
                self._items.append(FeedItem.from_event_data(value))
            except ValueError:
                continue
        if self._items:
            self.latest = self._items[-1]
            self._seen.extend(item.event_uid for item in self._items)

    async def async_save(self) -> None:
        """Persist complete raw callbacks and the useful derived fields."""
        await self._store.async_save(
            {
                "total_received": self.total_received,
                "total_duplicates": self.total_duplicates,
                "total_rejected": self.total_rejected,
                "items": [item.event_data() for item in self._items],
            }
        )

    def add_listener(self, listener: Callable[[FeedItem], None]) -> Callable[[], None]:
        """Register an entity update callback."""
        self._listeners.append(listener)

        def remove() -> None:
            self._listeners.remove(listener)

        return remove

    @property
    def items(self) -> tuple[FeedItem, ...]:
        """Return persisted callbacks, oldest first."""
        return tuple(self._items)

    def accept(self, item: FeedItem) -> bool:
        """Remember a payload and update listeners; return false for a replay."""
        if item.event_uid in self._seen:
            self.total_duplicates += 1
            return False
        self._seen.append(item.event_uid)
        self.latest = item
        self._items.append(item)
        self.total_received += 1
        for listener in tuple(self._listeners):
            listener(item)
        self.hass.async_create_task(self.async_save())
        if self.coordinator:
            self.hass.async_create_task(self.coordinator.async_request_refresh())
        return True

    def signature_is_valid(self, body: bytes, signature: str | None) -> bool:
        """Validate Starling V2's SHA512withRSA signature over raw JSON bytes."""
        if self.public_key is None or not signature:
            self.total_rejected += 1
            self.hass.async_create_task(self.async_save())
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
            self.hass.async_create_task(self.async_save())
            return False
        return True
