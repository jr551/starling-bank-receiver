"""Event platform for Starling Bank Receiver."""

from __future__ import annotations

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .models import FeedItem
from .runtime import ReceiverData

EVENT_TYPES = ["feed_item", "standing_order", "standing_order_payment"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ReceiverData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a last-received event entity."""
    async_add_entities([StarlingBankEvent(entry.entry_id, entry.runtime_data)])


class StarlingBankEvent(EventEntity):
    """Expose the most recent Starling event type."""

    _attr_has_entity_name = True
    _attr_event_types = EVENT_TYPES
    _attr_entity_description = EventEntityDescription(
        key="feed_item_received", name="Feed item received", icon="mdi:receipt-text-arrow-right"
    )

    def __init__(self, entry_id: str, data: ReceiverData) -> None:
        self.data = data
        self._attr_unique_id = f"{entry_id}_event"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

    async def async_added_to_hass(self) -> None:
        """Track received items."""
        self.async_on_remove(self.data.add_listener(self._handle_item))

    def _handle_item(self, item: FeedItem) -> None:
        event_type = item.webhook_type.lower()
        self.async_set_event_type(event_type)
