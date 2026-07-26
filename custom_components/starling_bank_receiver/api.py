"""Read-only Starling API client and update coordinator."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import logging
import math
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .bank_data import BankAccount, BankSnapshot, normalise_account

API_BASE_URL = "https://api.starlingbank.com/api/v2"
_LOGGER = logging.getLogger(__name__)
REQUIRED_READ_SCOPES = {
    "account-list:read",
    "balance:read",
    "savings-goal:read",
    "space:read",
}
DEFAULT_RATE_LIMIT_RETRY = 3600


class StarlingApiError(Exception):
    """Base error for a read-only Starling API request."""


class StarlingAuthenticationError(StarlingApiError):
    """The token is invalid or lacks a required read scope."""


class StarlingRateLimitError(StarlingApiError):
    """Starling rejected a request because the token exceeded its rate limit."""

    def __init__(self, retry_after: int | None) -> None:
        self.retry_after = retry_after
        detail = (
            f"; retrying in {retry_after} seconds"
            if retry_after is not None
            else ""
        )
        super().__init__(f"Starling API rate limit reached{detail}")


def _retry_after_seconds(value: str | None) -> int | None:
    """Convert an HTTP Retry-After value to a positive delay in seconds."""
    if not value:
        return None
    try:
        return max(1, int(value))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max(
        1,
        math.ceil((retry_at - datetime.now(timezone.utc)).total_seconds()),
    )


class StarlingApiClient:
    """Call only the read-only Starling account, balance, and spaces endpoints."""

    def __init__(self, session: ClientSession, token: str) -> None:
        self._session = session
        self._token = token

    async def _async_get(self, path: str) -> dict[str, Any]:
        """Fetch one JSON object using GET only."""
        try:
            async with self._session.get(
                f"{API_BASE_URL}/{path.lstrip('/')}",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/json",
                    "User-Agent": "HomeAssistant/starling-bank-receiver",
                },
                timeout=ClientTimeout(total=30),
            ) as response:
                if response.status in {401, 403}:
                    raise StarlingAuthenticationError(
                        "Starling rejected the API token or a required read scope"
                    )
                if response.status == 429:
                    raise StarlingRateLimitError(
                        _retry_after_seconds(response.headers.get("Retry-After"))
                    )
                response.raise_for_status()
                payload = await response.json()
        except (StarlingAuthenticationError, StarlingRateLimitError):
            raise
        except ClientResponseError as err:
            raise StarlingApiError(f"Starling API returned HTTP {err.status}") from err
        except (ClientError, TimeoutError, ValueError) as err:
            raise StarlingApiError("Unable to read the Starling API") from err
        if not isinstance(payload, dict):
            raise StarlingApiError("Starling API returned an unexpected response")
        return payload

    async def _async_fetch_account(self, account: Mapping[str, Any]) -> BankAccount:
        """Fetch balances and spaces for one account sequentially."""
        uid = account.get("accountUid")
        if not isinstance(uid, str) or not uid:
            raise StarlingApiError("Starling account response is missing accountUid")
        balance = await self._async_get(f"accounts/{uid}/balance")
        spaces = await self._async_get(f"account/{uid}/spaces")
        try:
            return normalise_account(account, balance, {}, spaces)
        except ValueError as err:
            raise StarlingApiError(str(err)) from err

    async def async_validate(self) -> None:
        """Validate authentication and required read scopes in one request."""
        identity = await self._async_get("identity/token")
        scopes = identity.get("scopes")
        if identity.get("authenticated") is not True or not isinstance(scopes, list):
            raise StarlingAuthenticationError("Starling API token is not authenticated")
        missing = REQUIRED_READ_SCOPES.difference(str(scope) for scope in scopes)
        if missing:
            raise StarlingAuthenticationError(
                "Starling API token is missing required read scopes"
            )

    async def async_fetch_snapshot(self) -> BankSnapshot:
        """Fetch every visible account, balance, and active space."""
        payload = await self._async_get("accounts")
        raw_accounts = payload.get("accounts")
        if not isinstance(raw_accounts, list) or not raw_accounts:
            raise StarlingApiError("Starling API returned no accounts")
        accounts = []
        for account in raw_accounts:
            if isinstance(account, Mapping):
                accounts.append(await self._async_fetch_account(account))
        return BankSnapshot(
            fetched_at=datetime.now(timezone.utc).isoformat(),
            accounts=tuple(accounts),
        )


class StarlingDataUpdateCoordinator(DataUpdateCoordinator[BankSnapshot]):
    """Refresh read-only Starling balances and spaces."""

    def __init__(
        self, hass: HomeAssistant, client: StarlingApiClient, scan_interval: int
    ) -> None:
        self._normal_update_interval = timedelta(seconds=scan_interval)
        super().__init__(
            hass,
            logger=_LOGGER,
            name="Starling Bank balances",
            update_interval=self._normal_update_interval,
        )
        self.client = client

    async def _async_update_data(self) -> BankSnapshot:
        """Fetch a fresh read-only snapshot."""
        try:
            snapshot = await self.client.async_fetch_snapshot()
            self.update_interval = self._normal_update_interval
            return snapshot
        except StarlingRateLimitError as err:
            retry_seconds = max(
                err.retry_after or DEFAULT_RATE_LIMIT_RETRY,
                int(self._normal_update_interval.total_seconds()),
            )
            self.update_interval = timedelta(seconds=retry_seconds)
            if self.data is not None:
                _LOGGER.warning(
                    "Starling rate limit reached; retaining the last balance "
                    "snapshot and retrying in %s seconds",
                    retry_seconds,
                )
                return self.data
            raise UpdateFailed(str(err)) from err
        except StarlingApiError as err:
            raise UpdateFailed(str(err)) from err
