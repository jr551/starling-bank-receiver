"""Config flow for Starling Bank Receiver."""

from __future__ import annotations

import secrets

from homeassistant.config_entries import ConfigFlow

from .const import CONF_WEBHOOK_SECRET, DOMAIN


class StarlingBankReceiverConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup without collecting any external credentials."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Create a single receiver with a high-entropy callback secret."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="Starling Bank feed",
            data={CONF_WEBHOOK_SECRET: secrets.token_urlsafe(32)},
        )
