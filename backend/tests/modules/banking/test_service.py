"""Transfers as a double-entry ledger.

The properties worth pinning down are the ones whose absence loses money:
both legs landing together, the balance being re-read rather than trusted, and
every refusal leaving both accounts exactly as they were.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.banking import service
from app.modules.banking import service as banking_service
from app.modules.investment import service as investment_service

NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


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


@pytest.fixture(autouse=True)
def no_investment_account(mocker):
    """These tests are about BANKING transfers.

    `transfer()` now checks whether either side is the investment account,
    because investment cash lives in a different table and reaching it was the
    whole point of the bridge. A mocked Session answers that lookup with a
    MagicMock, which then compares equal to nothing sensible -- so the tests
    say plainly that there is no investment account here.
    """
    import app.modules.investment.market_service as ms

    mocker.patch.object(ms, "account", return_value=None)


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


class TestSpendingReport:
    """Spending is derived from the ledger, never stored as its own total."""

    def _db(self, rows, accounts=None):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
            accounts if accounts is not None else [bank_account()]
        )
        db.execute.return_value.all.return_value = rows
        return db

    def test_categories_are_totalled(self):
        db = self._db([("Market", 5416.65), ("Kira", 14000.0)])
        result = service.spending_by_category(db, "user-1", since=NOW)
        assert result == [
            {"category": "Market", "amount": 5416.65},
            {"category": "Kira", "amount": 14000.0},
        ]

    def test_a_user_with_no_account_spends_nothing(self):
        assert service.spending_by_category(self._db([], accounts=[]), "ghost", since=NOW) == []

    def test_only_debits_are_counted(self):
        """A transfer between your own accounts writes both a debit and a
        credit; counting the debit would make moving your own money look like
        an expense."""
        db = self._db([])
        service.spending_by_category(db, "user-1", since=NOW)
        sql = str(db.execute.call_args.args[0]).upper()
        assert "DIRECTION" in sql

    def test_uncategorised_movements_are_excluded(self):
        """Salary and transfers carry no category; including them would make
        income read as spending."""
        db = self._db([])
        service.spending_by_category(db, "user-1", since=NOW)
        assert "IS NOT NULL" in str(db.execute.call_args.args[0]).upper()


class TestBalanceHistory:
    def _db(self, rows, accounts=None):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = (
            accounts if accounts is not None else [bank_account()]
        )
        db.execute.return_value.all.return_value = rows
        return db

    def test_points_are_returned_oldest_first(self):
        """The query reads newest-first for the LIMIT; a chart draws left to
        right."""
        db = self._db([(NOW, 300.0), (NOW, 200.0), (NOW, 100.0)])
        points = service.balance_history(db, "user-1")
        assert [p["balance"] for p in points] == [100.0, 200.0, 300.0]

    def test_the_stored_balance_is_read_not_replayed(self):
        db = self._db([(NOW, 48195.0)])
        service.balance_history(db, "user-1")
        assert "BALANCE_AFTER" in str(db.execute.call_args.args[0]).upper()

    def test_no_account_means_no_history(self):
        assert service.balance_history(self._db([], accounts=[]), "ghost") == []


class TestSavingsGoals:
    def test_goals_are_read_for_the_user(self):
        db = MagicMock(spec=Session)
        goals = [SimpleNamespace(id="g1", name="Araba")]
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = goals
        assert service.goals_for(db, "user-1") == goals


SINCE = datetime(2026, 7, 22, tzinfo=timezone.utc)


class TestIncomeTotal:
    """Income is the mirror of spending, and it has the same trap reversed.

    Moving your own money between two of your own accounts writes a CREDIT
    leg. Counting that as income would let anyone raise their apparent salary
    by shuffling funds back and forth, which would then flow straight into the
    savings rate on the Risk page.
    """

    def test_no_accounts_means_no_income(self, mock_db, mocker):
        mocker.patch.object(banking_service, "accounts_for", return_value=[])
        assert banking_service.income_total(mock_db, "user-1", SINCE) == 0.0

    def test_sums_external_credits(self, mock_db, mocker):
        mocker.patch.object(
            banking_service, "accounts_for",
            return_value=[SimpleNamespace(id="acct-1")],
        )
        mock_db.execute.return_value.scalar.return_value = 54286.0
        assert banking_service.income_total(mock_db, "user-1", SINCE) == 54286.0

    def test_no_movements_reports_zero_not_none(self, mock_db, mocker):
        mocker.patch.object(
            banking_service, "accounts_for",
            return_value=[SimpleNamespace(id="acct-1")],
        )
        mock_db.execute.return_value.scalar.return_value = None
        assert banking_service.income_total(mock_db, "user-1", SINCE) == 0.0


class TestPostAdjustment:
    """One-legged postings: an admin crediting the demo, a bill being paid.

    Still through the ledger. `UPDATE accounts SET balance` would move a number
    with nothing in the statement explaining it, and this module's own comment
    says the accounts are not the source of truth, the transactions are.
    """

    def _account(self, balance=1000.0):
        return SimpleNamespace(
            id="acc-1", account_number="TR-TEST-0001", iban="TR00", balance=balance,
            currency_code="TRY", status="active", user_id="u-1",
            updated_at=None,
        )

    def test_a_credit_raises_the_balance_and_writes_a_leg(self):
        db = MagicMock(spec=Session)
        account = self._account(1000.0)
        result = service.post_adjustment(db, account, 500.0, description="Yükleme")
        assert result["balance_after"] == 1500.0
        assert account.balance == 1500.0
        assert db.add.call_count == 2  # the transaction and its single leg

    def test_a_debit_lowers_it(self):
        db = MagicMock(spec=Session)
        account = self._account(1000.0)
        assert service.post_adjustment(db, account, -250.0, description="Fatura")["balance_after"] == 750.0

    def test_the_balance_may_not_go_negative(self):
        """An operator should be told they are over-withdrawing, not discover
        it as a negative balance on the customer's screen."""
        with pytest.raises(service.TransferError, match="eksiye"):
            service.post_adjustment(
                MagicMock(spec=Session), self._account(100.0), -500.0, description="x",
            )

    def test_zero_is_not_an_adjustment(self):
        with pytest.raises(service.TransferError):
            service.post_adjustment(
                MagicMock(spec=Session), self._account(), 0, description="x",
            )

    def test_the_transaction_type_is_the_caller_s(self):
        """Every non-transfer used to land as "duzeltme"."""
        db = MagicMock(spec=Session)
        service.post_adjustment(
            db, self._account(), -10.0, description="x", transaction_type="fatura",
        )
        written = [c.args[0] for c in db.add.call_args_list]
        assert any(getattr(o, "transaction_type", None) == "fatura" for o in written)

    def test_the_leg_records_the_balance_on_both_sides(self):
        """That is what makes a balance explainable after the fact."""
        db = MagicMock(spec=Session)
        service.post_adjustment(db, self._account(1000.0), 200.0, description="x")
        legs = [o for o in (c.args[0] for c in db.add.call_args_list)
                if hasattr(o, "balance_before")]
        assert legs[0].balance_before == 1000.0 and legs[0].balance_after == 1200.0


class TestAccountLookups:
    """Which account a caller means.

    `accounts_for(...)[0]` used to mean "the deposit account" and worked only
    while everyone had exactly one. With a vadeli account it is a coincidence,
    and a payment staged against the wrong pot is not a bug anyone would spot
    from the outside.
    """

    def _db(self, *accounts):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
            accounts[0] if accounts else None
        )
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = list(accounts)
        return db

    def test_the_deposit_account_is_found_by_type_not_by_position(self):
        vadesiz = SimpleNamespace(id="a-1", account_type="vadesiz")
        assert service.deposit_account(self._db(vadesiz), "u-1") is vadesiz

    def test_a_user_with_no_deposit_account_gets_none(self):
        assert service.deposit_account(self._db(), "u-1") is None

    def test_a_savings_account_is_opened_empty(self, mocker):
        """An account that arrives with money in it is a gift, not savings."""
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        account = service.ensure_savings_account(db, "u-1")
        assert account.account_type == "vadeli" and float(account.balance) == 0

    def test_an_existing_savings_account_is_reused(self):
        existing = SimpleNamespace(id="a-2", account_type="vadeli")
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = existing
        assert service.ensure_savings_account(db, "u-1") is existing


class TestPortfolioAccounts:
    """The unified list: banking rows plus the investment account."""

    def test_the_investment_account_is_included_and_flagged(self, mocker):
        import app.modules.investment.market_service as ms

        bank = SimpleNamespace(
            id="a-1", account_number="1", iban="TR1", account_type="vadesiz",
            currency_code="TRY", balance=100.0, interest_rate=None, term_days=None,
        )
        mocker.patch.object(service, "accounts_for", return_value=[bank])
        mocker.patch.object(ms, "account", return_value=SimpleNamespace(
            id="ia-1", account_number="TR-INV", iban="TR00INV", currency_code="TRY",
            cash_balance=250.0,
        ))
        rows = service.portfolio_accounts(MagicMock(spec=Session), "u-1")
        investment = [r for r in rows if r["is_investment"]]
        assert len(investment) == 1
        assert investment[0]["balance"] == 250.0
        assert investment[0]["account_type"] == service.INVESTMENT_ACCOUNT_TYPE
        # IBAN'ı artık var. None döndüğü sürece hesap "para gönder" ekranında
        # adreslenemiyor ve bankacılık arayüzü dökümünü isteyemiyordu.
        assert investment[0]["iban"] == "TR00INV"

    def test_an_investment_account_without_a_stored_iban_still_gets_one(self, mocker):
        """Migration öncesi açılmış bir hesap da adreslenebilir kalmalı.

        `iban` boşsa hesap numarasından aynı kuralla türetilir; ekranın
        elinde None ile hiçbir şey yapamayacağı bir satır kalmaz.
        """
        import app.modules.investment.market_service as ms

        mocker.patch.object(service, "accounts_for", return_value=[])
        mocker.patch.object(ms, "account", return_value=SimpleNamespace(
            id="ia-1", account_number="TR-INV", iban=None, currency_code="TRY",
            cash_balance=250.0,
        ))
        rows = service.portfolio_accounts(MagicMock(spec=Session), "u-1")
        assert rows[0]["iban"] == investment_service.iban_for("TR-INV")
        assert rows[0]["iban"].startswith("TR00")

    def test_a_user_with_no_investment_account_gets_only_banking_rows(self, mocker):
        import app.modules.investment.market_service as ms

        mocker.patch.object(service, "accounts_for", return_value=[])
        mocker.patch.object(ms, "account", return_value=None)
        assert service.portfolio_accounts(MagicMock(spec=Session), "u-1") == []


class TestInvestmentBridge:
    """Money crossing between banking and investment.

    Investment cash lives in `investment_accounts.cash_balance`, a different
    table, which is why no banking transfer could ever fund a trade. Both
    sides move in ONE transaction: a commit between them would leave money
    that has left the deposit account and not arrived at the other.
    """

    def _wire(self, mocker, *, bank_balance=1000.0, cash=500.0, currency="TRY"):
        import app.modules.investment.market_service as ms

        owner = SimpleNamespace(
            id="ia-1", account_number="TR-INV", currency_code=currency,
            cash_balance=cash,
        )
        mocker.patch.object(ms, "account", return_value=owner)
        bank = SimpleNamespace(
            id="a-1", user_id="u-1", account_number="1", iban="TR1",
            account_type="vadesiz", currency_code="TRY", balance=bank_balance,
            status="active", updated_at=None,
        )
        db = MagicMock(spec=Session)
        return db, bank, owner

    def test_money_leaves_banking_and_arrives_at_investing(self, mocker):
        db, bank, owner = self._wire(mocker)
        service.transfer_with_investment(
            db, user_id="u-1", bank_account=bank, amount=300, to_investment=True,
        )
        assert bank.balance == 700.0 and owner.cash_balance == 800.0

    def test_and_back_again(self, mocker):
        db, bank, owner = self._wire(mocker)
        service.transfer_with_investment(
            db, user_id="u-1", bank_account=bank, amount=200, to_investment=False,
        )
        assert bank.balance == 1200.0 and owner.cash_balance == 300.0

    def test_one_transaction_covers_both_sides(self, mocker):
        db, bank, _ = self._wire(mocker)
        service.transfer_with_investment(
            db, user_id="u-1", bank_account=bank, amount=100, to_investment=True,
        )
        assert db.commit.call_count == 1

    def test_the_banking_leg_records_before_and_after(self, mocker):
        db, bank, _ = self._wire(mocker)
        service.transfer_with_investment(
            db, user_id="u-1", bank_account=bank, amount=100, to_investment=True,
        )
        legs = [c.args[0] for c in db.add.call_args_list
                if type(c.args[0]).__name__ == "AccountTransaction"]
        assert legs[0].balance_before == 1000.0 and legs[0].balance_after == 900.0

    def test_an_overdraw_towards_investing_is_refused(self, mocker):
        db, bank, _ = self._wire(mocker, bank_balance=50.0)
        with pytest.raises(service.TransferError, match="yetersiz"):
            service.transfer_with_investment(
                db, user_id="u-1", bank_account=bank, amount=100, to_investment=True,
            )

    def test_an_overdraw_out_of_investing_is_refused(self, mocker):
        db, bank, _ = self._wire(mocker, cash=20.0)
        with pytest.raises(service.TransferError, match="Yatırım"):
            service.transfer_with_investment(
                db, user_id="u-1", bank_account=bank, amount=100, to_investment=False,
            )

    def test_crossing_currencies_is_refused_rather_than_applied_one_to_one(self, mocker):
        db, bank, _ = self._wire(mocker, currency="USD")
        with pytest.raises(service.TransferError, match="para birim"):
            service.transfer_with_investment(
                db, user_id="u-1", bank_account=bank, amount=10, to_investment=True,
            )

    def test_a_user_without_an_investment_account_is_refused(self, mocker):
        import app.modules.investment.market_service as ms

        mocker.patch.object(ms, "account", return_value=None)
        bank = SimpleNamespace(user_id="u-1", status="active", currency_code="TRY")
        with pytest.raises(service.TransferError, match="Yatırım hesabınız"):
            service.transfer_with_investment(
                MagicMock(spec=Session), user_id="u-1", bank_account=bank,
                amount=10, to_investment=True,
            )

    def test_someone_elses_account_is_refused(self, mocker):
        db, bank, _ = self._wire(mocker)
        bank.user_id = "someone-else"
        with pytest.raises(service.TransferError):
            service.transfer_with_investment(
                db, user_id="u-1", bank_account=bank, amount=10, to_investment=True,
            )

    def test_an_inactive_account_is_refused(self, mocker):
        db, bank, _ = self._wire(mocker)
        bank.status = "closed"
        with pytest.raises(service.TransferError, match="aktif"):
            service.transfer_with_investment(
                db, user_id="u-1", bank_account=bank, amount=10, to_investment=True,
            )

    def test_a_non_positive_amount_is_refused(self, mocker):
        db, bank, _ = self._wire(mocker)
        with pytest.raises(service.TransferError):
            service.transfer_with_investment(
                db, user_id="u-1", bank_account=bank, amount=0, to_investment=True,
            )


class TestTransferRoutesToTheBridge:
    """`transfer()` sends either side to the investment path when it should.

    Routed in the service rather than the router so every caller -- the panel,
    the chat's confirm, the admin -- behaves the same way.
    """

    def _wire(self, mocker, bank=None):
        import app.modules.investment.market_service as ms

        mocker.patch.object(ms, "account", return_value=SimpleNamespace(
            id="ia-1", account_number="TR-INV", currency_code="TRY", cash_balance=500.0,
        ))
        mocker.patch.object(service, "find_account", return_value=bank)
        return MagicMock(spec=Session)

    def test_a_transfer_to_the_investment_account_uses_the_bridge(self, mocker):
        bank = SimpleNamespace(
            id="a-1", user_id="u-1", account_number="1", iban="TR1",
            account_type="vadesiz", currency_code="TRY", balance=1000.0,
            status="active", updated_at=None,
        )
        db = self._wire(mocker, bank)
        bridged = mocker.patch.object(
            service, "transfer_with_investment", return_value={"reference_number": "T"},
        )
        service.transfer(
            db, user_id="u-1", source_reference="1",
            destination_reference="TR-INV", amount=100,
        )
        assert bridged.call_args.kwargs["to_investment"] is True

    def test_a_transfer_out_of_it_uses_the_bridge_the_other_way(self, mocker):
        bank = SimpleNamespace(
            id="a-1", user_id="u-1", account_number="1", currency_code="TRY",
            balance=0.0, status="active",
        )
        db = self._wire(mocker, bank)
        bridged = mocker.patch.object(
            service, "transfer_with_investment", return_value={"reference_number": "T"},
        )
        service.transfer(
            db, user_id="u-1", source_reference="TR-INV",
            destination_reference="1", amount=100,
        )
        assert bridged.call_args.kwargs["to_investment"] is False

    def test_an_unknown_other_side_is_refused(self, mocker):
        db = self._wire(mocker, None)
        with pytest.raises(service.TransferError, match="Hesap bulunamadı"):
            service.transfer(
                db, user_id="u-1", source_reference="nope",
                destination_reference="TR-INV", amount=100,
            )

    def test_investment_to_itself_is_refused(self, mocker):
        db = self._wire(mocker, SimpleNamespace(user_id="u-1", status="active"))
        with pytest.raises(service.TransferError, match="aynı olamaz"):
            service.transfer(
                db, user_id="u-1", source_reference="TR-INV",
                destination_reference="TR-INV", amount=100,
            )


class TestAccrueInterest:
    """Vadeli hesabın faizi.

    Ekranda `%42.50` ve `32 Gün` yazıyordu; ikisi de sabit metindi ve arkalarında
    ne bir sütun ne de bir işletme vardı. Vadenin sonunda bakiyeye hiçbir şey
    olmuyordu, çünkü faizi işleyen bir şey yoktu.
    """

    def _account(self, **kwargs):
        base = dict(
            id="acc-1", account_number="2000000000001", iban="TR00",
            balance=5000.0, currency_code="TRY", status="active", user_id="u-1",
            account_type="vadeli", interest_rate=38.0, term_days=1,
            last_accrued_at=None, updated_at=None,
        )
        base.update(kwargs)
        return SimpleNamespace(**base)

    def _db(self, accounts):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.filter.return_value.all.return_value = accounts
        db.query.return_value.filter.return_value.all.return_value = accounts
        return db

    def test_one_day_of_simple_interest_is_credited(self):
        """5.000 x %38 / 365 = 5,21."""
        account = self._account()
        posted = service.accrue_interest(self._db([account]))
        assert len(posted) == 1
        assert posted[0]["amount"] == pytest.approx(5.21)
        assert posted[0]["days"] == 1
        assert float(account.balance) == pytest.approx(5005.21)

    def test_it_is_written_as_a_movement_not_a_silent_balance_bump(self):
        """Dökümde açıklaması olmayan bir bakiye artışı, kimsenin hesabını
        veremeyeceği bir para demek."""
        db = self._db([self._account()])
        service.accrue_interest(db)
        # İşlem kaydı ve tek bacağı.
        assert db.add.call_count == 2
        written = [call.args[0] for call in db.add.call_args_list]
        assert any(getattr(row, "transaction_type", None) == "faiz" for row in written)

    def test_the_same_day_pays_only_once(self):
        """Yeniden başlatma faizi ikinci kez ödememeli."""
        now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
        account = self._account(last_accrued_at=now.replace(hour=1))
        assert service.accrue_interest(self._db([account]), now=now) == []
        assert float(account.balance) == pytest.approx(5000.0)

    def test_a_naive_timestamp_does_not_crash_the_comparison(self):
        """Saat dilimsiz bir damga UTC sayılır; karşılaştırma patlamamalı."""
        now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
        account = self._account(last_accrued_at=datetime(2026, 8, 28, 1, 0))
        assert service.accrue_interest(self._db([account]), now=now) == []

    def test_missed_days_are_paid_but_capped(self):
        """Uzun süre kapalı kalmış bir kurulum, açıldığında aylarca birikmiş
        faizi tek kalemde ödememeli: vaat edilen günlük bir vadeydi."""
        now = datetime(2026, 8, 28, tzinfo=timezone.utc)
        account = self._account(last_accrued_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
        posted = service.accrue_interest(self._db([account]), now=now)
        assert posted[0]["days"] == service.MAX_ACCRUAL_DAYS

    def test_an_empty_account_earns_nothing(self):
        assert service.accrue_interest(self._db([self._account(balance=0.0)])) == []

    def test_an_account_without_a_rate_is_skipped(self):
        """Varsayılan bir oran uydurmak, hesabın vaat etmediği bir getiriyi
        ödemek olurdu."""
        assert service.accrue_interest(self._db([self._account(interest_rate=0)])) == []

    def test_a_sub_kurus_accrual_still_advances_the_stamp(self):
        """Küçük bakiyede bir günün faizi kuruşun altında kalır. Sıfır tutarlı
        bir hareket dökümü kirletir; damga yine de ilerlemeli ki her gün
        yeniden denenmesin."""
        now = datetime(2026, 8, 28, tzinfo=timezone.utc)
        account = self._account(balance=0.01)
        assert service.accrue_interest(self._db([account]), now=now) == []
        assert account.last_accrued_at == now

    def test_it_can_be_narrowed_to_one_user(self):
        db = self._db([self._account()])
        service.accrue_interest(db, user_id="u-1")
        # user_id verildiğinde sorguya fazladan bir filtre ekleniyor.
        assert db.query.return_value.filter.return_value.filter.called


class TestCashFlow:
    """Ne girdi, ne çıktı, geriye ne kaldı.

    Bu sınıfın koruduğu iki şey, ikisi de aynı aileden -- YOKLUĞU BİR TESPİTE
    ÇEVİRMEMEK.

    `has_data`: ölçüldü, 23 kullanıcının 3'ünde bankacılık hareketi var.
    `income_events`: sıfır gelir "bu pencerede maaş yatmadı" da olabilir,
    "geliri yok" da; maaş aylık yattığı için otuz günlük bir pencere hiç maaş
    içermeyebiliyor ve gerçek bir kullanıcıda tam olarak bu ölçüldü.
    """

    def _db(self, mocker, bounds, income, categories, events):
        mocker.patch.object(
            banking_service, "accounts_for",
            return_value=[SimpleNamespace(id="acct-1", currency_code="TRY")],
        )
        mocker.patch.object(banking_service, "income_total", return_value=income)
        mocker.patch.object(
            banking_service, "spending_by_category", return_value=categories
        )
        db = MagicMock(spec=Session)
        db.execute.return_value.one.return_value = bounds
        db.execute.return_value.scalar_one.return_value = events
        return db

    BOUNDS = (datetime(2026, 5, 23, tzinfo=timezone.utc),
              datetime(2026, 8, 26, tzinfo=timezone.utc))
    CATEGORIES = [{"category": "Kira", "amount": 28000.0},
                  {"category": "Market", "amount": 10428.67}]

    def test_the_totals_agree_with_their_parts(self, mocker):
        db = self._db(mocker, self.BOUNDS, 112406.75, self.CATEGORIES, 4)
        flow = banking_service.cash_flow(db, "user-1")
        assert flow["expense_total"] == 38428.67
        assert flow["net_total"] == round(112406.75 - 38428.67, 2)

    def test_monthly_figures_are_the_window_divided_by_its_months(self, mocker):
        """Bölme SUNUCUDA. "Ayda ne kadar" sorusunun cevabı bu ve aritmetiği
        modele bırakmak, denetlenemeyen bir sayı bırakmak olurdu."""
        db = self._db(mocker, self.BOUNDS, 90000.0, self.CATEGORIES, 3)
        flow = banking_service.cash_flow(db, "user-1", days=90)
        assert flow["months_observed"] == 3.0
        assert flow["monthly_income"] == 30000.0

    def test_category_share_is_of_spending_not_income(self, mocker):
        """"Harcamamın %72'si kira" okunabilir bir cümle; "gelirimin %25'i
        kira" başka bir soru."""
        db = self._db(mocker, self.BOUNDS, 112406.75, self.CATEGORIES, 4)
        rent = banking_service.cash_flow(db, "user-1")["categories"][0]
        assert rent["share_percent"] == round(28000.0 / 38428.67 * 100, 1)

    def test_a_zero_spend_window_reports_no_share_rather_than_dividing(self, mocker):
        db = self._db(mocker, self.BOUNDS, 5000.0, [], 1)
        assert banking_service.cash_flow(db, "user-1")["categories"] == []

    def test_a_thin_window_carries_a_sentence_from_the_backend(self, mocker):
        """Kural önce prompt'a yazıldı; ölçüldüğünde model uygulamadı.

        İki maaş 90 güne bölününce kişinin kazandığının üçte bir altına
        düşüyor ve sayı verilmeden bu onun geliri gibi okunuyor -- prompt'a
        bırakılacak bir şey değil."""
        db = self._db(mocker, self.BOUNDS, 124000.0, self.CATEGORIES, 2)
        note = banking_service.cash_flow(db, "user-1", days=90)["coverage_note"]
        assert note is not None
        assert "2 gelir ödemesi" in note
        assert "altında kalabilir" in note

    def test_a_window_that_covers_the_cycle_carries_no_sentence(self, mocker):
        db = self._db(mocker, self.BOUNDS, 124000.0, self.CATEGORIES, 3)
        assert banking_service.cash_flow(db, "user-1", days=90)["coverage_note"] is None

    def test_zero_payments_get_their_own_sentence(self, mocker):
        """"Geliriniz yok" ile "bu pencereye ödeme düşmedi" farklı şeyler."""
        db = self._db(mocker, self.BOUNDS, 0.0, self.CATEGORIES, 0)
        note = banking_service.cash_flow(db, "user-1")["coverage_note"]
        assert "hiç gelir ödemesi görülmedi" in note
        assert "gelir olmadığı anlamına gelmez" in note

    def test_no_records_carries_no_sentence(self, mocker):
        mocker.patch.object(banking_service, "accounts_for", return_value=[])
        flow = banking_service.cash_flow(MagicMock(spec=Session), "ghost")
        assert flow["coverage_note"] is None

    def test_income_events_travel_with_the_total(self, mocker):
        """Sıfır gelirin hangi anlama geldiğini ayıran tek alan."""
        db = self._db(mocker, self.BOUNDS, 0.0, self.CATEGORIES, 0)
        flow = banking_service.cash_flow(db, "user-1")
        assert flow["income_total"] == 0.0
        assert flow["income_events"] == 0
        assert flow["has_data"] is True

    def test_a_user_with_no_account_has_no_data_rather_than_zeros(self, mocker):
        mocker.patch.object(banking_service, "accounts_for", return_value=[])
        flow = banking_service.cash_flow(MagicMock(spec=Session), "ghost")
        assert flow["has_data"] is False
        assert flow["income_total"] is None
        assert flow["net_total"] is None

    def test_an_account_with_no_movements_has_no_data_either(self, mocker):
        db = self._db(mocker, (None, None), 0.0, [], 0)
        assert banking_service.cash_flow(db, "user-1")["has_data"] is False

    def test_the_observed_range_is_reported(self, mocker):
        """Geçmişten geniş bir pencere, geniş olduğu görülebilsin diye."""
        db = self._db(mocker, self.BOUNDS, 1.0, self.CATEGORIES, 1)
        flow = banking_service.cash_flow(db, "user-1", days=365)
        assert flow["first_transaction_at"] == self.BOUNDS[0]
        assert flow["last_transaction_at"] == self.BOUNDS[1]

    def test_the_default_window_is_not_thirty_days(self, mocker):
        """30 günlük pencere gerçek bir kullanıcıda 0 TL gelir ve 6.697 TL
        gider gösteriyordu -- "geliriniz yok, ayda 6.697 harcıyorsunuz"."""
        assert banking_service.CASH_FLOW_WINDOW_DAYS == 90
        db = self._db(mocker, self.BOUNDS, 1.0, self.CATEGORIES, 1)
        assert banking_service.cash_flow(db, "user-1")["period_days"] == 90
