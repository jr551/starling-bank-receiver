"""Payload normalisation independent of Home Assistant."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


def _text(value: Any) -> str | None:
    """Return a bounded string value when present."""
    if value is None:
        return None
    return str(value)[:512]


@dataclass(frozen=True, slots=True)
class FeedItem:
    """A safe, useful projection of a Starling webhook payload."""

    event_uid: str
    webhook_type: str
    received_at: str | None
    feed_item_uid: str | None
    account_uid: str | None
    category_uid: str | None
    amount: int | None
    currency: str | None
    direction: str | None
    source: str | None
    source_sub_type: str | None
    status: str | None
    counterparty_name: str | None
    counterparty_type: str | None
    spending_category: str | None
    country: str | None
    transaction_time: str | None
    settlement_time: str | None
    card_last4: str | None

    def event_data(self) -> dict[str, Any]:
        """Return data suitable for the Home Assistant event bus."""
        return {key: value for key, value in asdict(self).items() if value is not None}


def parse_payload(payload: Mapping[str, Any]) -> FeedItem:
    """Validate and project a Starling V2 webhook payload."""
    event_uid = _text(payload.get("webhookEventUid"))
    webhook_type = _text(payload.get("webhookType"))
    if not event_uid or not webhook_type:
        raise ValueError("Missing webhookEventUid or webhookType")

    content = payload.get("content")
    if not isinstance(content, Mapping):
        content = {}
    amount = content.get("amount")
    amount = amount if isinstance(amount, Mapping) else {}
    card = content.get("masterCardFeedDetails")
    card = card if isinstance(card, Mapping) else {}

    minor_units = amount.get("minorUnits")
    if isinstance(minor_units, bool) or not isinstance(minor_units, int | float):
        minor_units = None

    return FeedItem(
        event_uid=event_uid,
        webhook_type=webhook_type,
        received_at=_text(payload.get("eventTimestamp")),
        feed_item_uid=_text(content.get("feedItemUid")),
        account_uid=_text(content.get("accountUid")),
        category_uid=_text(content.get("categoryUid")),
        amount=int(minor_units) if minor_units is not None else None,
        currency=_text(amount.get("currency")),
        direction=_text(content.get("direction")),
        source=_text(content.get("source")),
        source_sub_type=_text(content.get("sourceSubType")),
        status=_text(content.get("status")),
        counterparty_name=_text(content.get("counterPartyName")),
        counterparty_type=_text(content.get("counterPartyType")),
        spending_category=_text(content.get("spendingCategory")),
        country=_text(content.get("country")),
        transaction_time=_text(content.get("transactionTime")),
        settlement_time=_text(content.get("settlementTime")),
        card_last4=_text(card.get("cardLast4")),
    )
