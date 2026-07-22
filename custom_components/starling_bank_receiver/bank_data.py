"""Normalise read-only Starling account and space API responses."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


def _text(value: Any, fallback: str = "") -> str:
    """Return a bounded text value."""
    if value is None:
        return fallback
    return str(value)[:512]


def _minor_units(value: Any) -> int:
    """Read a Starling money object's integer minor units."""
    if not isinstance(value, Mapping):
        return 0
    minor_units = value.get("minorUnits")
    if isinstance(minor_units, bool) or not isinstance(minor_units, int | float):
        return 0
    return int(minor_units)


def _currency(value: Any, fallback: str = "GBP") -> str:
    """Read a Starling money object's currency."""
    if not isinstance(value, Mapping):
        return fallback
    return _text(value.get("currency"), fallback).upper()


def major_units(minor_units: int) -> Decimal:
    """Convert integer minor units to an exact major-unit Decimal."""
    return Decimal(minor_units) / Decimal(100)


@dataclass(frozen=True, slots=True)
class BankSpace:
    """One Starling savings goal or spending space."""

    uid: str
    account_uid: str
    account_name: str
    name: str
    kind: str
    state: str
    currency: str
    balance_minor_units: int
    target_minor_units: int | None
    sort_order: int | None

    @property
    def balance(self) -> Decimal:
        """Return the balance in major units."""
        return major_units(self.balance_minor_units)

    @property
    def target(self) -> Decimal | None:
        """Return the optional target in major units."""
        if self.target_minor_units is None:
            return None
        return major_units(self.target_minor_units)

    @property
    def progress_percent(self) -> float | None:
        """Return progress towards a non-zero target."""
        if not self.target_minor_units:
            return None
        return round(self.balance_minor_units / self.target_minor_units * 100, 2)


@dataclass(frozen=True, slots=True)
class BankAccount:
    """One Starling account and its current read-only balances."""

    uid: str
    name: str
    account_type: str
    currency: str
    default_category_uid: str
    cleared_minor_units: int
    effective_minor_units: int
    pending_minor_units: int
    accepted_overdraft_minor_units: int
    spaces: tuple[BankSpace, ...]

    @property
    def effective_balance(self) -> Decimal:
        """Return the effective balance in major units."""
        return major_units(self.effective_minor_units)


@dataclass(frozen=True, slots=True)
class BankSnapshot:
    """A complete read-only API snapshot."""

    fetched_at: str
    accounts: tuple[BankAccount, ...]

    @property
    def spaces(self) -> tuple[BankSpace, ...]:
        """Return all spaces across all accounts."""
        return tuple(space for account in self.accounts for space in account.spaces)

    @property
    def total_space_minor_units(self) -> int:
        """Return the total held across all spaces."""
        return sum(space.balance_minor_units for space in self.spaces)

    @property
    def total_space_currency(self) -> str | None:
        """Return the common spaces currency, or none for mixed currencies."""
        currencies = {space.currency for space in self.spaces}
        if len(currencies) == 1:
            return next(iter(currencies))
        return None

    def account(self, uid: str) -> BankAccount | None:
        """Find an account by UID."""
        return next((account for account in self.accounts if account.uid == uid), None)

    def space(self, uid: str) -> BankSpace | None:
        """Find a space by UID."""
        return next((space for space in self.spaces if space.uid == uid), None)


def normalise_account(
    account: Mapping[str, Any],
    balance: Mapping[str, Any],
    savings_goals: Mapping[str, Any],
    spaces: Mapping[str, Any],
) -> BankAccount:
    """Normalise the four read-only Starling responses for one account."""
    account_uid = _text(account.get("accountUid"))
    if not account_uid:
        raise ValueError("Starling account response is missing accountUid")
    account_name = _text(
        account.get("name"), _text(account.get("accountType"), "Starling account")
    )
    account_currency = _text(account.get("currency"), "GBP").upper()

    by_uid: dict[str, BankSpace] = {}
    for raw in savings_goals.get("savingsGoalList") or []:
        if not isinstance(raw, Mapping):
            continue
        uid = _text(raw.get("savingsGoalUid"))
        if not uid:
            continue
        total = raw.get("totalSaved")
        target = raw.get("target")
        target_minor_units = _minor_units(target)
        by_uid[uid] = BankSpace(
            uid=uid,
            account_uid=account_uid,
            account_name=account_name,
            name=_text(raw.get("name"), "Savings space"),
            kind="savings_goal",
            state=_text(raw.get("state")),
            currency=_currency(total, _currency(target, account_currency)),
            balance_minor_units=_minor_units(total),
            target_minor_units=target_minor_units or None,
            sort_order=None,
        )

    for raw in spaces.get("savingsGoals") or []:
        if not isinstance(raw, Mapping):
            continue
        uid = _text(raw.get("savingsGoalUid"))
        if uid in by_uid:
            current = by_uid[uid]
            order = raw.get("sortOrder")
            by_uid[uid] = BankSpace(
                uid=current.uid,
                account_uid=current.account_uid,
                account_name=current.account_name,
                name=current.name,
                kind=current.kind,
                state=current.state,
                currency=current.currency,
                balance_minor_units=current.balance_minor_units,
                target_minor_units=current.target_minor_units,
                sort_order=order
                if isinstance(order, int) and not isinstance(order, bool)
                else None,
            )
        elif uid:
            total = raw.get("totalSaved")
            target = raw.get("target")
            target_minor_units = _minor_units(target)
            order = raw.get("sortOrder")
            by_uid[uid] = BankSpace(
                uid=uid,
                account_uid=account_uid,
                account_name=account_name,
                name=_text(raw.get("name"), "Savings space"),
                kind="savings_goal",
                state=_text(raw.get("state")),
                currency=_currency(total, _currency(target, account_currency)),
                balance_minor_units=_minor_units(total),
                target_minor_units=target_minor_units or None,
                sort_order=order
                if isinstance(order, int) and not isinstance(order, bool)
                else None,
            )

    for raw in spaces.get("spendingSpaces") or []:
        if not isinstance(raw, Mapping):
            continue
        uid = _text(raw.get("spaceUid"))
        if not uid:
            continue
        total = raw.get("balance") or raw.get("totalSaved")
        order = raw.get("sortOrder")
        by_uid[uid] = BankSpace(
            uid=uid,
            account_uid=account_uid,
            account_name=account_name,
            name=_text(raw.get("name"), "Spending space"),
            kind="spending_space",
            state=_text(raw.get("state")),
            currency=_currency(total, account_currency),
            balance_minor_units=_minor_units(total),
            target_minor_units=None,
            sort_order=order
            if isinstance(order, int) and not isinstance(order, bool)
            else None,
        )

    ordered_spaces = tuple(
        sorted(
            by_uid.values(),
            key=lambda item: (
                item.sort_order is None,
                item.sort_order if item.sort_order is not None else 0,
                item.name.casefold(),
            ),
        )
    )
    return BankAccount(
        uid=account_uid,
        name=account_name,
        account_type=_text(account.get("accountType")),
        currency=account_currency,
        default_category_uid=_text(account.get("defaultCategory")),
        cleared_minor_units=_minor_units(balance.get("clearedBalance")),
        effective_minor_units=_minor_units(balance.get("effectiveBalance")),
        pending_minor_units=_minor_units(balance.get("pendingTransactions")),
        accepted_overdraft_minor_units=_minor_units(balance.get("acceptedOverdraft")),
        spaces=ordered_spaces,
    )
