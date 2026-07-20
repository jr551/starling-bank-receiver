"""Sensor platform for Starling Bank Receiver."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import callback_base_url
from .const import DOMAIN
from .runtime import ReceiverData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ReceiverData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the latest-feed sensor."""
    async_add_entities([StarlingBankFeedSensor(hass, entry.entry_id, entry.runtime_data)])


class StarlingBankFeedSensor(SensorEntity):
    """Show the latest accepted Starling callback."""

    _attr_has_entity_name = True
    _attr_name = "Feed"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:bank-transfer-in"

    def __init__(self, hass: HomeAssistant, entry_id: str, data: ReceiverData) -> None:
        self.hass = hass
        self.data = data
        self._attr_unique_id = f"{entry_id}_feed"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

    async def async_added_to_hass(self) -> None:
        """Update when a callback arrives."""
        self.async_on_remove(self.data.add_listener(lambda _: self.async_write_ha_state()))

    @property
    def native_value(self) -> datetime | None:
        """Use the received time as the sensor's timestamp."""
        item = self.data.latest
        if not item or not item.received_at:
            return None
        return datetime.fromisoformat(item.received_at.replace("Z", "+00:00"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Provide the copyable callback URL and normalised latest item."""
        attributes: dict[str, Any] = {
            "payload_url": callback_base_url(self.hass, self.data),
            "accepted_callbacks": self.data.total_received,
            "ignored_replays": self.data.total_duplicates,
        }
        if self.data.latest:
            attributes["latest"] = self.data.latest.event_data()
        return attributes
