"""Set up Starling Bank Receiver."""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import get_url

from .api import StarlingApiClient, StarlingDataUpdateCoordinator
from .const import (
    CONF_API_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_WEBHOOK_SECRET,
    CONF_WEBHOOK_PUBLIC_KEY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_FEED_ITEM_RECEIVED,
    EVENT_WEBHOOK_RECEIVED,
    PLATFORMS,
    ROUTE_TO_WEBHOOK_TYPE,
)
from .models import parse_payload
from .runtime import ReceiverData

type StarlingConfigEntry = ConfigEntry[ReceiverData]


async def async_setup_entry(hass: HomeAssistant, entry: StarlingConfigEntry) -> bool:
    """Set up an entry and its unauthenticated secret callback route."""
    data = ReceiverData(
        hass,
        entry.entry_id,
        entry.data[CONF_WEBHOOK_SECRET],
        entry.options.get(CONF_WEBHOOK_PUBLIC_KEY),
    )
    await data.async_restore()
    api_token = str(entry.options.get(CONF_API_TOKEN) or "").strip()
    if api_token:
        data.coordinator = StarlingDataUpdateCoordinator(
            hass,
            StarlingApiClient(async_get_clientsession(hass), api_token),
            int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        await data.coordinator.async_refresh()
    entry.runtime_data = data
    runtime = hass.data.setdefault(DOMAIN, {})
    runtime[entry.entry_id] = data
    if not runtime.get("view_registered"):
        hass.http.register_view(StarlingWebhookView(hass))
        runtime["view_registered"] = True

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Starling Bank",
        name="Starling Bank feed",
        model="Webhook and read-only API receiver" if api_token else "Webhook receiver",
        sw_version="0.3.0",
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: StarlingConfigEntry) -> bool:
    """Unload platforms. HTTP views remain harmless and return 404 after unload."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: StarlingConfigEntry) -> None:
    """Reload after a webhook public key is added or replaced."""
    await hass.config_entries.async_reload(entry.entry_id)


def callback_base_url(hass: HomeAssistant, data: ReceiverData) -> str | None:
    """Return the base URL to paste into Starling's Developer Portal."""
    try:
        base_url = get_url(hass, prefer_external=True)
    except Exception:  # Home Assistant has no externally configured URL.
        return None
    return f"{base_url}/api/{DOMAIN}/{data.secret}"


class StarlingWebhookView(HomeAssistantView):
    """Receive Starling's event-suffixed V2 callbacks."""

    requires_auth = False
    name = f"api:{DOMAIN}:webhook"
    url = f"/api/{DOMAIN}/{{secret}}/{{event_type}}"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def post(
        self, request: web.Request, secret: str, event_type: str
    ) -> web.Response:
        """Validate a callback, emit it locally, then acknowledge immediately."""
        data = next(
            (
                candidate
                for candidate in self.hass.data.get(DOMAIN, {}).values()
                if isinstance(candidate, ReceiverData) and candidate.secret == secret
            ),
            None,
        )
        if data is None or event_type not in ROUTE_TO_WEBHOOK_TYPE:
            raise web.HTTPNotFound()
        try:
            body = await request.read()
            payload: dict[str, Any] = json.loads(body)
            item = parse_payload(payload)
        except (json.JSONDecodeError, ValueError, TypeError):
            raise web.HTTPBadRequest(text="Expected a Starling V2 JSON webhook") from None
        if not data.signature_is_valid(body, request.headers.get("X-Hook-Signature")):
            raise web.HTTPUnauthorized(text="Invalid or unconfigured Starling signature")

        if item.webhook_type != ROUTE_TO_WEBHOOK_TYPE[event_type]:
            raise web.HTTPBadRequest(text="Callback path and webhookType do not match")
        if not data.accept(item):
            return web.Response(status=204)

        event_data = item.event_data()
        self.hass.bus.async_fire(EVENT_WEBHOOK_RECEIVED, event_data)
        if item.webhook_type == "FEED_ITEM":
            self.hass.bus.async_fire(EVENT_FEED_ITEM_RECEIVED, event_data)
        return web.Response(status=204)
