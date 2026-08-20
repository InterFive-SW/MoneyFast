"""Transfers as a double-entry ledger.

The properties worth pinning down are the ones whose absence loses money:
both legs landing together, the balance being re-read rather than trusted, and
every refusal leaving both accounts exactly as they were.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.banking import service


def bank_account(
    account_id="acc-1",
    user_id="user-1",
    number="1000000000001",
    iban="TR001000000000010000000010",
    balance=50000.0,
    currency="TRY",
    status="active",
):
    return SimpleNamespace(
        id=account_id, user_id=user_id, account_number=number, iban=iban,
        account_type="vadesiz", currency_code=currency, balance=balance,
        status=status, updated_at=None,
    )


class Ledger:
    """A Session double that resolves two accounts by reference and records
    everything added."""

    def __init__(self, source=None, destination=None):
        self.db = MagicMock(spec=Session)
        self.added = []
        self.db.add.side_effect = self.added.append
        lookups = [source, destination]
        self.db.query.return_value.filter.return_value.first.side_effect = lookups

    @property
    def legs(self):
        return [a for a in self.added if type(a).__name__ == "AccountTransaction"]

    @property
    def transaction(self):
        return next(a for a in self.added if type(a).__name__ == "BankTransaction")


class TestSuccessfulTransfer:
    def test_money_leaves_one_account_and_arrives_at_the_other(self):
        source, destination = bank_account(balance=50000.0), bank_account(
            "acc-2", "user-2", "1000000000002", "TR002", balance=1000.0
        )
        service.transfer(
            Ledger(source, destination).db, "user-1",
            source.account_number, destination.account_number, 250.0,
        )
        # An external transfer carries a fee, which leaves the sender too.
        assert float(source.balance) == pytest.approx(50000.0 - 250.0 - service.EXTERNAL_TRANSFER_FEE)
        assert float(destination.balance) == pytest.approx(1250.0)

    def test_both_legs_are_written(self):
        """One leg alone is money that left an account and arrived nowhere."""
        ledger = Ledger(bank_account(), bank_account("acc-2", "user-2", "1000000000002", "TR002"))
        service.transfer(ledger.db, "user-1", "1000000000001", "1000000000002", 100.0)
        directions = sorted(leg.direction for leg in ledger.legs)
        assert directions == ["CREDIT", "DEBIT"]

    def test_each_leg_records_the_balance_either_side_of_it(self):
        """Stored, not recomputed: this is what lets someone say later what an
        account held at a given moment without replaying its whole history."""
        source = bank_account(balance=5000.0)
        destination = bank_account("acc-2", "user-2", "1000000000002", "TR002", balance=200.0)
        ledger = Ledger(source, destination)
        service.transfer(ledger.db, "user-1", "1000000000001", "1000000000002", 100.0)

        debit = next(leg for leg in ledger.legs if leg.direction == "DEBIT")
        credit = next(leg for leg in ledger.legs if leg.direction == "CREDIT")
        assert float(debit.balance_before) == 5000.0
        assert float(debit.balance_after) == pytest.approx(5000.0 - 100.0 - service.EXTERNAL_TRANSFER_FEE)
        assert float(credit.balance_before) == 200.0
        assert float(credit.balance_after) == pytest.approx(300.0)

    def test_the_legs_point_at_the_same_transaction(self):
        ledger = Ledger(bank_account(), bank_account("acc-2", "user-2", "1000000000002", "TR002"))
        service.transfer(ledger.db, "user-1", "1000000000001", "1000000000002", 100.0)
        assert {leg.transaction_id for leg in ledger.legs} == {ledger.transaction.id}

    def test_a_reference_number_is_issued(self):
        ledger = Ledger(bank_account(), bank_account("acc-2", "user-2", "1000000000002", "TR002"))
        result = service.transfer(ledger.db, "user-1", "1000000000001", "1000000000002", 100.0)
        assert result["reference_number"].startswith("TRF-")
        assert result["status"] == "completed"

    def test_one_commit_covers_the_whole_transfer(self):
        """Committing the debit before the credit is how half a transfer
        becomes permanent."""
        ledger = Ledger(bank_account(), bank_account("acc-2", "user-2", "1000000000002", "TR002"))
        service.transfer(ledger.db, "user-1", "1000000000001", "1000000000002", 100.0)
        assert ledger.db.commit.call_count == 1

    def test_moving_between_your_own_accounts_is_free(self):
        """Charging someone to move their own money between their own accounts
        is a fee with no service behind it."""
        source = bank_account(balance=1000.0)
        destination = bank_account("acc-2", "user-1", "1000000000002", "TR002", balance=0.0)
        service.transfer(Ledger(source, destination).db, "user-1", "1000000000001", "1000000000002", 100.0)
        assert float(source.balance) == pytest.approx(900.0)

    def test_an_own_transfer_is_recorded_as_a_virman(self):
        ledger = Ledger(bank_account(), bank_account("acc-2", "user-1", "1000000000002", "TR002"))
        service.transfer(ledger.db, "user-1", "1000000000001", "1000000000002", 100.0)
        assert ledger.transaction.transaction_type == "virman"

    def test_a_transfer_to_someone_else_is_a_havale(self):
        ledger = Ledger(bank_account(), bank_account("acc-2", "user-2", "1000000000002", "TR002"))
        service.transfer(ledger.db, "user-1", "1000000000001", "1000000000002", 100.0)
        assert ledger.transaction.transaction_type == "havale"


class TestRefusals:
    """Every refusal must leave both balances untouched."""

    def _assert_untouched(self, source, destination, action):
        before = float(source.balance), float(destination.balance)
        with pytest.raises(service.TransferError) as excinfo:
            action()
        assert (float(source.balance), float(destination.balance)) == before
        return str(excinfo.value)

    def test_insufficient_balance_is_refused(self):
        source = bank_account(balance=100.0)
        destination = bank_account("acc-2", "user-2", "1000000000002", "TR002")
        message = self._assert_untouched(
            source, destination,
            lambda: service.transfer(
                Ledger(source, destination).db, "user-1",
                "1000000000001", "1000000000002", 500.0,
            ),
        )
        assert "yetersiz" in message.lower()

    def test_the_fee_counts_towards_the_balance_check(self):
        """İK-07: the balance must cover the amount AND the fee. Exactly the
        amount is not enough when a fee applies."""
        source = bank_account(balance=100.0)
        destination = bank_account("acc-2", "user-2", "1000000000002", "TR002")
        with pytest.raises(service.TransferError):
            service.transfer(
                Ledger(source, destination).db, "user-1",
                "1000000000001", "1000000000002", 100.0,
            )

    def test_sending_to_yourself_is_refused(self):
        """Always a mistake, and processing it writes a ledger entry saying
        nothing happened."""
        same = bank_account()
        with pytest.raises(service.TransferError) as excinfo:
            service.transfer(
                Ledger(same, same).db, "user-1",
                "1000000000001", "1000000000001", 10.0,
            )
        assert "aynı" in str(excinfo.value).lower()

    def test_sending_from_an_account_you_do_not_own_is_refused(self):
        """Reported as "not found": confirming that someone else's account
        exists is already more than the caller should learn."""
        stranger = bank_account(user_id="someone-else")
        destination = bank_account("acc-2", "user-1", "1000000000002", "TR002")
        with pytest.raises(service.TransferError) as excinfo:
            service.transfer(
                Ledger(stranger, destination).db, "user-1",
                "1000000000001", "1000000000002", 10.0,
            )
        assert "bulunamadı" in str(excinfo.value)

    def test_an_unknown_source_is_refused(self):
        with pytest.raises(service.TransferError):
            service.transfer(Ledger(None, None).db, "user-1", "NOPE", "1000000000002", 10.0)

    def test_an_unknown_destination_is_refused(self):
        with pytest.raises(service.TransferError) as excinfo:
            service.transfer(Ledger(bank_account(), None).db, "user-1", "1000000000001", "NOPE", 10.0)
        assert "Alıcı" in str(excinfo.value)

    def test_an_inactive_source_is_refused(self):
        with pytest.raises(service.TransferError):
            service.transfer(
                Ledger(bank_account(status="closed"), bank_account("acc-2")).db,
                "user-1", "1000000000001", "1000000000002", 10.0,
            )

    def test_an_inactive_destination_is_refused(self):
        with pytest.raises(service.TransferError):
            service.transfer(
                Ledger(bank_account(), bank_account("acc-2", "user-2", status="frozen")).db,
                "user-1", "1000000000001", "1000000000002", 10.0,
            )

    @pytest.mark.parametrize("amount", [0.0, -50.0, None])
    def test_a_non_positive_amount_is_refused(self, amount):
        with pytest.raises(service.TransferError):
            service.transfer(Ledger().db, "user-1", "1000000000001", "1000000000002", amount)

    def test_crossing_currencies_is_refused_rather_than_applied_one_to_one(self):
        """Applying 1:1 across currencies is the bug this codebase already
        paid for once on the trading side."""
        source = bank_account(currency="TRY")
        destination = bank_account("acc-2", "user-2", "1000000000002", "TR002", currency="USD")
        with pytest.raises(service.TransferError) as excinfo:
            service.transfer(
                Ledger(source, destination).db, "user-1",
                "1000000000001", "1000000000002", 10.0,
            )
        assert "para birim" in str(excinfo.value).lower()


class TestAccountLookup:
    def test_an_account_is_found_by_number(self):
        db = MagicMock(spec=Session)
        target = bank_account()
        db.query.return_value.filter.return_value.first.return_value = target
        assert service.find_account(db, "1000000000001") is target

    def test_an_iban_is_accepted_with_or_without_spaces(self):
        """People paste IBANs formatted for reading."""
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = bank_account()
        assert service.find_account(db, "TR00 1000 0000 0001") is not None

    @pytest.mark.parametrize("reference", ["", "   ", None])
    def test_an_empty_reference_is_not_a_lookup(self, reference):
        db = MagicMock(spec=Session)
        assert service.find_account(db, reference) is None
        assert not db.query.called


class TestEnsureAccount:
    def test_an_existing_account_is_reused(self):
        db = MagicMock(spec=Session)
        existing = bank_account()
        db.query.return_value.filter.return_value.first.return_value = existing
        assert service.ensure_account(db, "user-1") is existing
        assert not db.add.called

    def test_a_new_account_opens_with_a_balance_and_an_iban(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        account = service.ensure_account(db, "user-2")
        assert float(account.balance) == service.STARTING_BALANCE
        assert account.iban.startswith("TR")
        assert account.account_type == "vadesiz"

    def test_two_users_get_distinct_numbers(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        first = service.ensure_account(db, "aaaaaaaa-1111-2222-3333-444444444444")
        second = service.ensure_account(db, "bbbbbbbb-1111-2222-3333-444444444444")
        assert first.account_number != second.account_number
        assert first.iban != second.iban

    def test_accounts_for_reads_the_users_own(self):
        db = MagicMock(spec=Session)
        rows = [bank_account()]
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = rows
        assert service.accounts_for(db, "user-1") == rows


class TestIdentifierDerivation:
    """Account numbers and IBANs are unique-constrained, so a collision is a
    failed registration, not a cosmetic problem."""

    def test_ibans_do_not_collide_for_ids_differing_only_in_letters(self):
        """User ids are hex. Keeping only their digits made "aaaa…" and
        "bbbb…" produce the same IBAN."""
        first = service._iban_for(f"1{service._digits_for('aaaaaaaa-1111', 12)}")
        second = service._iban_for(f"1{service._digits_for('bbbbbbbb-1111', 12)}")
        assert first != second

    def test_the_derivation_is_stable(self):
        """A second call must return the same account, not open a new one."""
        assert service._digits_for("user-1", 12) == service._digits_for("user-1", 12)

    def test_account_numbers_are_numeric(self):
        assert service._digits_for("28bfbc42-ef4f", 12).isdigit()

    def test_an_iban_is_the_documented_length(self):
        iban = service._iban_for("1123456789012")
        assert iban.startswith("TR00")
        assert len(iban) <= 34


class TestModelDefaults:
    """The column default factories.

    Called directly: SQLAlchemy invokes them at flush, and the service tests
    use session doubles that never flush.
    """

    def test_ids_are_generated_client_side_and_are_distinct(self):
        """Client-side ids let a transaction's legs reference it before the
        INSERT lands."""
        from app.modules.banking import models

        assert models._uuid() != models._uuid()

    def test_timestamps_are_timezone_aware(self):
        """A naive timestamp compared against an aware one raises at runtime."""
        from app.modules.banking import models

        assert models._now().tzinfo is not None
