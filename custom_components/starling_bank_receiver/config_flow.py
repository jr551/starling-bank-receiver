"""Config flow for Starling Bank Receiver."""

from __future__ import annotations

import secrets

import voluptuous as vol
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .api import StarlingApiClient, StarlingApiError, StarlingAuthenticationError
from .const import (
    CONF_API_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_WEBHOOK_PUBLIC_KEY,
    CONF_WEBHOOK_SECRET,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)


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
    """Configure webhook verification and optional read-only API access."""

    def __init__(self) -> None:
        self._errors: dict[str, str] = {}

    async def async_step_init(self, user_input=None):
        """Accept a public key and an optional personal read-only API token."""
        if user_input is not None:
            current = dict(self.config_entry.options)
            submitted_key = str(user_input.get(CONF_WEBHOOK_PUBLIC_KEY) or "").strip()
            submitted_token = str(user_input.get(CONF_API_TOKEN) or "").strip()
            key = submitted_key or str(current.get(CONF_WEBHOOK_PUBLIC_KEY) or "")
            token = submitted_token or str(current.get(CONF_API_TOKEN) or "")
            scan_interval = int(
                user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            )
            if key:
                try:
                    load_pem_public_key(key.encode())
                except ValueError:
                    self._errors["base"] = "invalid_public_key"
            if not self._errors and token:
                client = StarlingApiClient(async_get_clientsession(self.hass), token)
                try:
                    await client.async_validate()
                except StarlingAuthenticationError:
                    self._errors["base"] = "invalid_auth"
                except StarlingApiError:
                    self._errors["base"] = "cannot_connect"
            if not self._errors:
                return self.async_create_entry(
                    data={
                        CONF_WEBHOOK_PUBLIC_KEY: key,
                        CONF_API_TOKEN: token,
                        CONF_SCAN_INTERVAL: scan_interval,
                    }
                )
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_WEBHOOK_PUBLIC_KEY,
                    default="",
                ): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
                vol.Optional(CONF_API_TOKEN, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=3600,
                        step=60,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="seconds",
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=self._errors
        )
