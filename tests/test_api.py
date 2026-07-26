"""Tests for Starling API rate-limit handling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import unittest

from custom_components.starling_bank_receiver.api import (
    StarlingApiClient,
    StarlingRateLimitError,
    _retry_after_seconds,
)


class _FakeResponse:
    status = 429
    headers = {"Retry-After": "120"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _FakeSession:
    def get(self, *args, **kwargs):
        return _FakeResponse()


class RetryAfterTests(unittest.TestCase):
    def test_delta_seconds(self):
        self.assertEqual(_retry_after_seconds("120"), 120)

    def test_http_date(self):
        future = datetime.now(timezone.utc) + timedelta(seconds=120)
        delay = _retry_after_seconds(format_datetime(future, usegmt=True))
        self.assertIsNotNone(delay)
        self.assertGreaterEqual(delay, 118)
        self.assertLessEqual(delay, 120)

    def test_invalid_value(self):
        self.assertIsNone(_retry_after_seconds("not-a-delay"))


class ClientRateLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_429_exposes_retry_delay(self):
        client = StarlingApiClient(_FakeSession(), "not-a-real-token")
        with self.assertRaises(StarlingRateLimitError) as raised:
            await client._async_get("accounts")
        self.assertEqual(raised.exception.retry_after, 120)


if __name__ == "__main__":
    unittest.main()
