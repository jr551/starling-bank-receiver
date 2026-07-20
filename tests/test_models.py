"""Tests for payload normalisation without requiring Home Assistant."""

import importlib.util
from pathlib import Path
import sys
import unittest

_models_path = Path(__file__).parents[1] / "custom_components/starling_bank_receiver/models.py"
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

    def test_envelope_is_required(self) -> None:
        with self.assertRaises(ValueError):
            parse_payload({"content": {}})


if __name__ == "__main__":
    unittest.main()
