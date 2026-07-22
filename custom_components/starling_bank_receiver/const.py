"""Constants for Starling Bank Receiver."""

from typing import Final

DOMAIN: Final = "starling_bank_receiver"
PLATFORMS: Final = ["sensor", "event"]

CONF_API_TOKEN: Final = "api_token"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_WEBHOOK_SECRET: Final = "webhook_secret"
CONF_WEBHOOK_PUBLIC_KEY: Final = "webhook_public_key"
DEFAULT_SCAN_INTERVAL: Final = 300
MIN_SCAN_INTERVAL: Final = 60
EVENT_WEBHOOK_RECEIVED: Final = f"{DOMAIN}.webhook_received"
EVENT_FEED_ITEM_RECEIVED: Final = f"{DOMAIN}.feed_item_received"

ROUTE_TO_WEBHOOK_TYPE: Final = {
    "feed-item": "FEED_ITEM",
    "standing-order": "STANDING_ORDER",
    "standing-order-payment": "STANDING_ORDER_PAYMENT",
}
