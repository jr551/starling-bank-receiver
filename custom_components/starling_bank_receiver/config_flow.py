"""Config flow for Starling Bank Receiver."""

from __future__ import annotations

import secrets

import voluptuous as vol
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.helpers import selector

from .const import CONF_WEBHOOK_PUBLIC_KEY, CONF_WEBHOOK_SECRET, DOMAIN


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

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the public-key configuration form."""
        return StarlingBankReceiverOptionsFlow()


class StarlingBankReceiverOptionsFlow(OptionsFlow):
    """Configure the Starling-created public verification key."""

    def __init__(self) -> None:
        self._errors: dict[str, str] = {}

    async def async_step_init(self, user_input=None):
        """Accept the PEM public key shown by Starling after webhook creation."""
        if user_input is not None:
            key = user_input[CONF_WEBHOOK_PUBLIC_KEY].strip()
            try:
                load_pem_public_key(key.encode())
            except ValueError:
                self._errors["base"] = "invalid_public_key"
            else:
                return self.async_create_entry(data={CONF_WEBHOOK_PUBLIC_KEY: key})
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_WEBHOOK_PUBLIC_KEY,
                    default=self.config_entry.options.get(CONF_WEBHOOK_PUBLIC_KEY, ""),
                ): selector.TextSelector(selector.TextSelectorConfig(multiline=True))
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=self._errors)
