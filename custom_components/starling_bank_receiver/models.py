"""Payload normalisation independent of Home Assistant."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any


def _text(value: Any) -> str | None:
    """Return a bounded string value when present."""
    if value is None:
        return None
    return str(value)[:512]


def _json_copy(value: Any) -> Any:
    """Make a JSON-safe copy without dropping fields from Starling's callback."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_copy(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_copy(item) for item in value]
    return str(value)


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
    raw_payload: dict[str, Any]

    def event_data(self) -> dict[str, Any]:
        """Return data suitable for the Home Assistant event bus."""
        return {key: value for key, value in asdict(self).items() if value is not None}

    @classmethod
    def from_event_data(cls, data: Mapping[str, Any]) -> FeedItem:
        """Restore a previously stored normalised item from entity attributes."""
        fields = cls.__dataclass_fields__
        restored = {field: data.get(field) for field in fields}
        amount = restored.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, int | float):
            restored["amount"] = None
        elif amount is not None:
            restored["amount"] = int(amount)
        if not restored.get("event_uid") or not restored.get("webhook_type"):
            raise ValueError("Stored item is missing its event identity")
        raw_payload = restored.get("raw_payload")
        restored["raw_payload"] = (
            _json_copy(raw_payload) if isinstance(raw_payload, Mapping) else {}
        )
        return cls(**restored)

    @property
    def transaction_type(self) -> str:
        """Return a concise, human-readable Starling transaction type."""
        source = (self.source or "").upper()
        webhook_type = self.webhook_type.upper()
        if source in {"MASTER_CARD", "CARD_PAYMENT", "CARD"} or self.card_last4:
            return "Card payment"
        if source == "DIRECT_DEBIT":
            return "Direct debit"
        if source in {"STANDING_ORDER", "SCHEDULED_PAYMENT"} or (
            "STANDING_ORDER" in webhook_type
        ):
            return "Standing order"
        if source in {"INTERNAL_TRANSFER", "INTERNAL"}:
            return "Internal transfer"
        if source in {"CASH_WITHDRAWAL", "CASH_MACHINE"}:
            return "Cash withdrawal"
        if source in {"FASTER_PAYMENTS_IN", "BANK_TRANSFER_IN"}:
            return "Bank transfer in"
        if source in {"FASTER_PAYMENTS_OUT", "BANK_TRANSFER_OUT"}:
            return "Bank transfer out"
        if source in {"FASTER_PAYMENTS", "BANK_TRANSFER"}:
            return "Bank transfer"
        if self.direction == "IN":
            return "Money in"
        if self.direction == "OUT":
            return "Money out"
        return source.replace("_", " ").title() if source else "Bank transaction"

    @property
    def symbol(self) -> str:
        """Return an easily-scanned symbol for the transaction."""
        source = (self.source or "").upper()
        if source in {"MASTER_CARD", "CARD_PAYMENT", "CARD"} or self.card_last4:
            return "💳"
        if source == "DIRECT_DEBIT":
            return "🏦"
        if source in {"STANDING_ORDER", "SCHEDULED_PAYMENT"} or "STANDING_ORDER" in (
            self.webhook_type.upper()
        ):
            return "🔁"
        if source in {"INTERNAL_TRANSFER", "INTERNAL"}:
            return "🔄"
        if source in {"CASH_WITHDRAWAL", "CASH_MACHINE"}:
            return "🏧"
        if self.direction == "IN":
            return "💰"
        if self.direction == "OUT":
            return "↗️"
        return "💷"

    @property
    def amount_display(self) -> str:
        """Format the minor-unit amount as a GBP display value."""
        if self.amount is None:
            return "£0.00"
        value = Decimal(self.amount) / Decimal(100)
        if (self.currency or "GBP").upper() == "GBP":
            return f"£{value:,.2f}"
        return f"{value:,.2f} {(self.currency or '').upper()}".strip()

    @property
    def summary(self) -> str:
        """Return the state shown in Home Assistant dashboards."""
        parts = [self.symbol, self.amount_display, self.transaction_type]
        if self.counterparty_name:
            parts.append(self.counterparty_name)
        return " • ".join(parts)


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
        raw_payload=_json_copy(payload),
    )
