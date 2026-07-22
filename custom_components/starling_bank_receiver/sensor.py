"""Sensor platform for Starling Bank Receiver."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import callback_base_url
from .api import StarlingDataUpdateCoordinator
from .bank_data import BankAccount, BankSnapshot, BankSpace, major_units
from .const import DOMAIN
from .models import FeedItem
from .runtime import ReceiverData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ReceiverData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the latest-feed sensor."""
    async_add_entities(
        [
            StarlingBankFeedSensor(hass, entry.entry_id, entry.runtime_data),
            StarlingBankAmountSensor(entry.entry_id, entry.runtime_data),
        ]
    )
    if entry.runtime_data.coordinator:
        manager = StarlingBankSensorManager(
            entry.entry_id, entry.runtime_data.coordinator, async_add_entities
        )
        manager.add_entities()
        entry.async_on_unload(
            entry.runtime_data.coordinator.async_add_listener(manager.add_entities)
        )


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
        self.async_on_remove(
            self.data.add_listener(lambda _: self.async_write_ha_state())
        )
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
            "🐷": "mdi:piggy-bank",
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
            "signature_validation": "enabled"
            if self.data.public_key
            else "not_configured",
        }
        if self.data.latest:
            attributes["latest"] = self.data.latest.event_data()
            attributes["transaction_type"] = self.data.latest.transaction_type
            attributes["symbol"] = self.data.latest.symbol
            attributes["amount_gbp"] = self.data.latest.amount_display
        return attributes


class StarlingBankAmountSensor(SensorEntity):
    """Expose the latest amount as a signed numeric value for automations."""

    _attr_has_entity_name = True
    _attr_name = "Latest amount"
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, entry_id: str, data: ReceiverData) -> None:
        self.data = data
        self._attr_unique_id = f"{entry_id}_latest_amount"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

    async def async_added_to_hass(self) -> None:
        """Update whenever a callback is accepted."""
        self.async_on_remove(
            self.data.add_listener(lambda _: self.async_write_ha_state())
        )
        self.async_write_ha_state()

    @property
    def native_value(self) -> Decimal | None:
        """Return positive money in and negative money out."""
        item = self.data.latest
        return item.signed_amount if item else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Use the transaction currency as the monetary unit."""
        item = self.data.latest
        return (item.currency or "GBP").upper() if item else "GBP"

    @property
    def icon(self) -> str:
        """Match the numeric sensor icon to the transaction type."""
        item = self.data.latest
        if item and item.symbol == "🐷":
            return "mdi:piggy-bank"
        if item and (item.direction or "").upper() == "IN":
            return "mdi:cash-plus"
        return "mdi:cash-minus"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the useful automation fields without requiring raw JSON parsing."""
        item = self.data.latest
        if not item:
            return {}
        return {
            key: value
            for key, value in {
                "direction": item.direction,
                "transaction_type": item.transaction_type,
                "source": item.source,
                "source_sub_type": item.source_sub_type,
                "status": item.status,
                "counterparty_name": item.counterparty_name,
                "spending_category": item.spending_category,
                "reference": item.reference,
                "transaction_time": item.transaction_time,
            }.items()
            if value is not None
        }


class StarlingBankSensorManager:
    """Add account and space sensors discovered by the coordinator."""

    def __init__(
        self,
        entry_id: str,
        coordinator: StarlingDataUpdateCoordinator,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        self.entry_id = entry_id
        self.coordinator = coordinator
        self.async_add_entities = async_add_entities
        self._known: set[str] = set()

    def add_entities(self) -> None:
        """Add newly discovered read-only API entities."""
        entities: list[SensorEntity] = []
        if "spaces_total" not in self._known:
            self._known.add("spaces_total")
            entities.append(StarlingSpacesTotalSensor(self.entry_id, self.coordinator))
        snapshot = self.coordinator.data
        if snapshot:
            for account in snapshot.accounts:
                key = f"account:{account.uid}"
                if key not in self._known:
                    self._known.add(key)
                    entities.append(
                        StarlingAccountBalanceSensor(
                            self.entry_id, self.coordinator, account
                        )
                    )
                for space in account.spaces:
                    key = f"space:{space.uid}"
                    if key not in self._known:
                        self._known.add(key)
                        entities.append(
                            StarlingSpaceBalanceSensor(
                                self.entry_id, self.coordinator, space
                            )
                        )
        if entities:
            self.async_add_entities(entities)


class StarlingBankCoordinatorSensor(
    CoordinatorEntity[StarlingDataUpdateCoordinator], SensorEntity
):
    """Base class for read-only Starling API monetary sensors."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2

    def __init__(
        self, entry_id: str, coordinator: StarlingDataUpdateCoordinator
    ) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

    @property
    def snapshot(self) -> BankSnapshot | None:
        """Return the current coordinator snapshot."""
        return self.coordinator.data

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the refresh timestamp, never the API credential."""
        return {"last_synced": self.snapshot.fetched_at} if self.snapshot else {}


class StarlingSpacesTotalSensor(StarlingBankCoordinatorSensor):
    """Show the total held in all Starling spaces."""

    _attr_name = "Spaces total"
    _attr_icon = "mdi:piggy-bank"

    def __init__(
        self, entry_id: str, coordinator: StarlingDataUpdateCoordinator
    ) -> None:
        super().__init__(entry_id, coordinator)
        self._attr_unique_id = f"{entry_id}_spaces_total"

    @property
    def available(self) -> bool:
        """Require a successful snapshot with one common currency."""
        return bool(
            super().available and self.snapshot and self.snapshot.total_space_currency
        )

    @property
    def native_value(self) -> Decimal | None:
        """Return the total held in spaces."""
        if not self.snapshot:
            return None
        return major_units(self.snapshot.total_space_minor_units)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the common spaces currency."""
        return self.snapshot.total_space_currency if self.snapshot else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Include snapshot counts."""
        attributes = super().extra_state_attributes
        if self.snapshot:
            attributes.update(
                {
                    "account_count": len(self.snapshot.accounts),
                    "space_count": len(self.snapshot.spaces),
                }
            )
        return attributes


class StarlingAccountBalanceSensor(StarlingBankCoordinatorSensor):
    """Show one account's effective balance."""

    def __init__(
        self,
        entry_id: str,
        coordinator: StarlingDataUpdateCoordinator,
        account: BankAccount,
    ) -> None:
        super().__init__(entry_id, coordinator)
        self.account_uid = account.uid
        self._attr_unique_id = f"{entry_id}_account_{account.uid}_balance"
        self._attr_name = f"{account.name} balance"
        self._attr_icon = (
            "mdi:piggy-bank" if account.account_type == "SAVINGS" else "mdi:bank"
        )

    @property
    def account(self) -> BankAccount | None:
        """Return the current account snapshot."""
        return self.snapshot.account(self.account_uid) if self.snapshot else None

    @property
    def available(self) -> bool:
        """Require the account to remain in a successful snapshot."""
        return bool(super().available and self.account)

    @property
    def native_value(self) -> Decimal | None:
        """Return the effective balance including pending transactions."""
        return self.account.effective_balance if self.account else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the account currency."""
        return self.account.currency if self.account else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose useful balance components without account identifiers."""
        attributes = super().extra_state_attributes
        account = self.account
        if account:
            attributes.update(
                {
                    "account_type": account.account_type,
                    "cleared_balance": float(major_units(account.cleared_minor_units)),
                    "pending_transactions": float(
                        major_units(account.pending_minor_units)
                    ),
                    "accepted_overdraft": float(
                        major_units(account.accepted_overdraft_minor_units)
                    ),
                    "space_count": len(account.spaces),
                }
            )
        return attributes


class StarlingSpaceBalanceSensor(StarlingBankCoordinatorSensor):
    """Show one savings goal or spending space balance."""

    def __init__(
        self,
        entry_id: str,
        coordinator: StarlingDataUpdateCoordinator,
        space: BankSpace,
    ) -> None:
        super().__init__(entry_id, coordinator)
        self.space_uid = space.uid
        self._attr_unique_id = f"{entry_id}_space_{space.uid}_balance"
        self._attr_name = f"{space.name} space"
        self._attr_icon = (
            "mdi:wallet" if space.kind == "spending_space" else "mdi:piggy-bank"
        )

    @property
    def space(self) -> BankSpace | None:
        """Return the current space snapshot."""
        return self.snapshot.space(self.space_uid) if self.snapshot else None

    @property
    def available(self) -> bool:
        """Require the space to remain in a successful snapshot."""
        return bool(super().available and self.space)

    @property
    def native_value(self) -> Decimal | None:
        """Return the current space balance."""
        return self.space.balance if self.space else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the space currency."""
        return self.space.currency if self.space else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose space metadata and optional goal progress."""
        attributes = super().extra_state_attributes
        space = self.space
        if space:
            attributes.update(
                {
                    "account_name": space.account_name,
                    "space_type": space.kind,
                    "space_state": space.state,
                }
            )
            if space.target is not None:
                attributes["target"] = float(space.target)
                attributes["progress_percent"] = space.progress_percent
        return attributes
