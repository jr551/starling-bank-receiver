"""Tests for payload normalisation."""

import unittest

from custom_components.starling_bank_receiver.models import parse_payload


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

    def test_envelope_is_required(self) -> None:
        with self.assertRaises(ValueError):
            parse_payload({"content": {}})


if __name__ == "__main__":
    unittest.main()
