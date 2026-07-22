"""Tests for payload normalisation without requiring Home Assistant."""

import importlib.util
from pathlib import Path
import sys
import unittest

_models_path = (
    Path(__file__).parents[1] / "custom_components/starling_bank_receiver/models.py"
)
_spec = importlib.util.spec_from_file_location("starling_models", _models_path)
assert _spec and _spec.loader
_models = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _models
_spec.loader.exec_module(_models)
parse_payload = _models.parse_payload


class ParsePayloadTests(unittest.TestCase):
    """Ensure public payload shapes are accepted without real account data."""

    def test_feed_item_is_normalised(self) -> None:
        item = parse_payload(
            {
                "webhookEventUid": "event-1",
                "webhookType": "FEED_ITEM",
                "eventTimestamp": "2026-01-01T00:00:00Z",
                "content": {
                    "feedItemUid": "item-1",
                    "amount": {"currency": "GBP", "minorUnits": 1234},
                    "direction": "OUT",
                    "masterCardFeedDetails": {"cardLast4": "1234"},
                },
            }
        )
        self.assertEqual(item.amount, 1234)
        self.assertEqual(item.currency, "GBP")
        self.assertEqual(item.card_last4, "1234")
        self.assertEqual(item.summary, "💳 • £12.34 • Card payment")
        self.assertEqual(item.raw_payload["content"]["amount"]["minorUnits"], 1234)
        self.assertEqual(item.signed_amount, _models.Decimal("-12.34"))

    def test_gbp_transfer_summary_has_a_type_and_symbol(self) -> None:
        item = parse_payload(
            {
                "webhookEventUid": "event-2",
                "webhookType": "FEED_ITEM",
                "content": {
                    "amount": {"currency": "GBP", "minorUnits": 50000},
                    "direction": "IN",
                    "source": "FASTER_PAYMENTS_IN",
                    "counterPartyName": "Example Ltd",
                },
            }
        )
        self.assertEqual(item.summary, "💰 • £500.00 • Bank transfer in • Example Ltd")
        self.assertEqual(item.signed_amount, _models.Decimal("500"))

    def test_realistic_round_up_is_classified_and_enriched(self) -> None:
        item = parse_payload(
            {
                "webhookEventUid": "event-round-up",
                "webhookType": "FEED_ITEM",
                "eventTimestamp": "2026-07-22T14:56:01Z",
                "content": {
                    "feedItemUid": "item-round-up",
                    "amount": {"currency": "GBP", "minorUnits": 66},
                    "sourceAmount": {"currency": "GBP", "minorUnits": 66},
                    "direction": "IN",
                    "source": "INTERNAL_TRANSFER",
                    "sourceSubType": "ROUND_UP",
                    "status": "SETTLED",
                    "counterPartyName": "Savings space",
                    "counterPartyType": "CATEGORY",
                    "reference": "Round up",
                    "updatedAt": "2026-07-22T14:56:02Z",
                    "hasAttachment": False,
                    "receiptPresent": False,
                },
            }
        )
        self.assertEqual(item.transaction_type, "Round up")
        self.assertEqual(item.symbol, "🐷")
        self.assertEqual(item.summary, "🐷 • £0.66 • Round up • Savings space")
        self.assertEqual(item.source_amount, 66)
        self.assertEqual(item.source_currency, "GBP")
        self.assertEqual(item.reference, "Round up")
        self.assertFalse(item.has_attachment)
        self.assertFalse(item.receipt_present)

    def test_envelope_is_required(self) -> None:
        with self.assertRaises(ValueError):
            parse_payload({"content": {}})


if __name__ == "__main__":
    unittest.main()
