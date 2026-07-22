"""Tests for read-only Starling account and space normalisation."""

import importlib.util
from pathlib import Path
import sys
import unittest

_module_path = (
    Path(__file__).parents[1] / "custom_components/starling_bank_receiver/bank_data.py"
)
_spec = importlib.util.spec_from_file_location("starling_bank_data", _module_path)
assert _spec and _spec.loader
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)


class BankDataTests(unittest.TestCase):
    """Ensure real API response shapes become stable entity data."""

    def test_account_balances_and_spaces_are_normalised(self) -> None:
        account = _module.normalise_account(
            {
                "accountUid": "account-1",
                "name": "Joint Account",
                "accountType": "PRIMARY",
                "currency": "GBP",
                "defaultCategory": "category-1",
            },
            {
                "clearedBalance": {"currency": "GBP", "minorUnits": 12345},
                "effectiveBalance": {"currency": "GBP", "minorUnits": 12000},
                "pendingTransactions": {"currency": "GBP", "minorUnits": 345},
                "acceptedOverdraft": {"currency": "GBP", "minorUnits": 0},
            },
            {},
            {
                "savingsGoals": [
                    {
                        "savingsGoalUid": "goal-1",
                        "name": "Holiday",
                        "state": "ACTIVE",
                        "sortOrder": 2,
                        "totalSaved": {"currency": "GBP", "minorUnits": 12550},
                        "target": {"currency": "GBP", "minorUnits": 50000},
                    }
                ],
                "spendingSpaces": [
                    {
                        "spaceUid": "space-1",
                        "name": "Connected card",
                        "state": "ACTIVE",
                        "sortOrder": 1,
                        "balance": {"currency": "GBP", "minorUnits": 2500},
                    }
                ],
            },
        )
        self.assertEqual(account.effective_balance, _module.Decimal("120"))
        self.assertEqual(account.cleared_minor_units, 12345)
        self.assertEqual(account.pending_minor_units, 345)
        self.assertEqual(len(account.spaces), 2)
        self.assertEqual(account.spaces[0].kind, "spending_space")
        holiday = next(space for space in account.spaces if space.uid == "goal-1")
        self.assertEqual(holiday.balance, _module.Decimal("125.5"))
        self.assertEqual(holiday.target, _module.Decimal("500"))
        self.assertEqual(holiday.progress_percent, 25.1)

    def test_snapshot_totals_and_lookup(self) -> None:
        space = _module.BankSpace(
            uid="goal-1",
            account_uid="account-1",
            account_name="Joint Account",
            name="Holiday",
            kind="savings_goal",
            state="ACTIVE",
            currency="GBP",
            balance_minor_units=12345,
            target_minor_units=None,
            sort_order=None,
        )
        account = _module.BankAccount(
            uid="account-1",
            name="Joint Account",
            account_type="PRIMARY",
            currency="GBP",
            default_category_uid="category-1",
            cleared_minor_units=0,
            effective_minor_units=0,
            pending_minor_units=0,
            accepted_overdraft_minor_units=0,
            spaces=(space,),
        )
        snapshot = _module.BankSnapshot("2026-01-01T00:00:00Z", (account,))
        self.assertEqual(snapshot.total_space_minor_units, 12345)
        self.assertEqual(snapshot.total_space_currency, "GBP")
        self.assertIs(snapshot.account("account-1"), account)
        self.assertIs(snapshot.space("goal-1"), space)


if __name__ == "__main__":
    unittest.main()
