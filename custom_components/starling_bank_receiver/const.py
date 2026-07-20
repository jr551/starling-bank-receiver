"""Constants for Starling Bank Receiver."""

from typing import Final

DOMAIN: Final = "starling_bank_receiver"
PLATFORMS: Final = ["sensor", "event"]

CONF_WEBHOOK_SECRET: Final = "webhook_secret"
CONF_WEBHOOK_PUBLIC_KEY: Final = "webhook_public_key"
EVENT_WEBHOOK_RECEIVED: Final = f"{DOMAIN}.webhook_received"
EVENT_FEED_ITEM_RECEIVED: Final = f"{DOMAIN}.feed_item_received"

ROUTE_TO_WEBHOOK_TYPE: Final = {
    "feed-item": "FEED_ITEM",
    "standing-order": "STANDING_ORDER",
    "standing-order-payment": "STANDING_ORDER_PAYMENT",
}
