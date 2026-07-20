"""Sensor platform for Starling Bank Receiver."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import callback_base_url
from .const import DOMAIN
from .models import FeedItem
from .runtime import ReceiverData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ReceiverData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the latest-feed sensor."""
    async_add_entities([StarlingBankFeedSensor(hass, entry.entry_id, entry.runtime_data)])


class StarlingBankFeedSensor(SensorEntity, RestoreEntity):
    """Show the latest accepted Starling callback."""

    _attr_has_entity_name = True
    _attr_name = "Latest transaction"

    def __init__(self, hass: HomeAssistant, entry_id: str, data: ReceiverData) -> None:
        self.hass = hass
        self.data = data
        self._attr_unique_id = f"{entry_id}_feed"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

    async def async_added_to_hass(self) -> None:
        """Restore the last transaction, then update when a callback arrives."""
        await super().async_added_to_hass()
        if self.data.latest is None:
            last_state = await self.async_get_last_state()
            latest = last_state.attributes.get("latest") if last_state else None
            if isinstance(latest, dict):
                try:
                    self.data.latest = FeedItem.from_event_data(latest)
                except ValueError:
                    pass
        self.async_on_remove(self.data.add_listener(lambda _: self.async_write_ha_state()))
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        """Show a readable GBP payment summary rather than a generic event name."""
        item = self.data.latest
        return item.summary if item else None

    @property
    def icon(self) -> str:
        """Match the dashboard icon to the latest transaction type."""
        item = self.data.latest
        if not item:
            return "mdi:bank-transfer"
        return {
            "💳": "mdi:credit-card",
            "🏦": "mdi:bank",
            "🔁": "mdi:repeat",
            "🔄": "mdi:swap-horizontal",
            "🏧": "mdi:cash",
            "💰": "mdi:cash-plus",
        }.get(item.symbol, "mdi:bank-transfer-out")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Provide the copyable callback URL and normalised latest item."""
        attributes: dict[str, Any] = {
            "payload_url": callback_base_url(self.hass, self.data),
            "accepted_callbacks": self.data.total_received,
            "ignored_replays": self.data.total_duplicates,
            "rejected_callbacks": self.data.total_rejected,
            "stored_callbacks": len(self.data.items),
            "signature_validation": "enabled" if self.data.public_key else "not_configured",
        }
        if self.data.latest:
            attributes["latest"] = self.data.latest.event_data()
            attributes["transaction_type"] = self.data.latest.transaction_type
            attributes["symbol"] = self.data.latest.symbol
            attributes["amount_gbp"] = self.data.latest.amount_display
        return attributes
