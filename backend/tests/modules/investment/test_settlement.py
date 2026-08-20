"""Applying a confirmed trade to cash and holdings.

Confirming used to set two columns and commit — no cash moved, no position
changed — while the order list displayed "Gerçekleşti". These tests pin down
the arithmetic that makes that word true, and the refusals that keep it from
being true by accident.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.investment import service


def proposal(
    transaction_type="BUY",
    symbol="THYAO",
    quantity=10,
    net_amount=3022.26,
    reference_price=301.75,
):
    estimate = {}
    if net_amount is not None:
        estimate["net_amount"] = net_amount
    if reference_price is not None:
        estimate["reference_price"] = reference_price
    return SimpleNamespace(
        id="PROP-1",
        transaction_type=transaction_type,
        symbol=symbol,
        quantity=quantity,
        payload={"estimate": estimate} if estimate else {},
    )


def account(cash=25000.0):
    return SimpleNamespace(id="acct-1", cash_balance=cash)


class Fixture:
    """A Session double resolving one product and (optionally) one position."""

    def __init__(self, position=None, product=SimpleNamespace(id="prod-1", symbol="THYAO")):
        self.db = MagicMock(spec=Session)
        self.deleted = []
        self.added = []
        chain = self.db.query.return_value.filter.return_value
        # First lookup is the product, second is the position.
        chain.first.side_effect = [product, position]
        self.db.delete.side_effect = self.deleted.append
        self.db.add.side_effect = self.added.append


class TestBuy:
    def test_cash_falls_by_the_net_amount(self):
        """The net includes commission and BSMV, because those leave the
        account too."""
        acct = account(25000.0)
        service.settle(Fixture().db, proposal(net_amount=3022.26), acct)
        assert float(acct.cash_balance) == pytest.approx(21977.74)

    def test_a_new_holding_is_created(self):
        fix = Fixture(position=None)
        service.settle(fix.db, proposal(quantity=10), account())
        assert len(fix.added) == 1
        assert float(fix.added[0].quantity) == 10

    def test_the_cost_basis_is_the_reference_price_not_the_all_in_net(self):
        """Fees are an expense, not part of what the shares are worth. Folding
        them into the basis would overstate the break-even price."""
        fix = Fixture(position=None)
        service.settle(fix.db, proposal(quantity=10, net_amount=3022.26, reference_price=301.75), account())
        assert float(fix.added[0].average_buy_price) == pytest.approx(301.75)

    def test_adding_to_a_holding_uses_a_weighted_average(self):
        """The old basis keeps its weight in the shares it applies to.
        Overwriting with the latest price would erase what the position cost."""
        position = SimpleNamespace(quantity=100.0, average_buy_price=200.0, updated_at=None)
        fix = Fixture(position=position)
        service.settle(fix.db, proposal(quantity=100, reference_price=300.0), account(100000.0))
        # 100 @ 200 plus 100 @ 300 -> 200 @ 250
        assert float(position.quantity) == 200
        assert float(position.average_buy_price) == pytest.approx(250.0)

    def test_a_purchase_over_the_balance_is_refused(self):
        acct = account(1000.0)
        with pytest.raises(service.SettlementError) as excinfo:
            service.settle(Fixture().db, proposal(net_amount=3022.26), acct)
        assert "yetersiz" in str(excinfo.value).lower()
        assert float(acct.cash_balance) == 1000.0, "a refused trade must not move cash"

    def test_spending_the_balance_exactly_is_allowed(self):
        acct = account(3022.26)
        service.settle(Fixture().db, proposal(net_amount=3022.26), acct)
        assert float(acct.cash_balance) == pytest.approx(0.0)


class TestSell:
    def test_cash_rises_by_the_net_amount(self):
        position = SimpleNamespace(quantity=100.0, average_buy_price=200.0, updated_at=None)
        acct = account(5000.0)
        service.settle(
            Fixture(position=position).db,
            proposal(transaction_type="SELL", quantity=10, net_amount=2990.0),
            acct,
        )
        assert float(acct.cash_balance) == pytest.approx(7990.0)

    def test_the_holding_shrinks(self):
        position = SimpleNamespace(quantity=100.0, average_buy_price=200.0, updated_at=None)
        service.settle(
            Fixture(position=position).db,
            proposal(transaction_type="SELL", quantity=30),
            account(),
        )
        assert float(position.quantity) == 70

    def test_selling_does_not_change_the_average_cost(self):
        """A sale does not alter what the remaining shares cost to acquire."""
        position = SimpleNamespace(quantity=100.0, average_buy_price=200.0, updated_at=None)
        service.settle(
            Fixture(position=position).db,
            proposal(transaction_type="SELL", quantity=30),
            account(),
        )
        assert float(position.average_buy_price) == 200.0

    def test_selling_everything_removes_the_row(self):
        """Average cost is meaningless without shares; a zero-quantity row
        would linger in the portfolio as a holding of nothing."""
        position = SimpleNamespace(quantity=50.0, average_buy_price=200.0, updated_at=None)
        fix = Fixture(position=position)
        service.settle(fix.db, proposal(transaction_type="SELL", quantity=50), account())
        assert fix.deleted == [position]

    def test_float_dust_still_closes_the_position(self):
        """A full sell can leave 1e-15 behind. A row claiming a billionth of a
        share is noise pretending to be a holding."""
        position = SimpleNamespace(quantity=50.0 + 1e-12, average_buy_price=200.0, updated_at=None)
        fix = Fixture(position=position)
        service.settle(fix.db, proposal(transaction_type="SELL", quantity=50), account())
        assert fix.deleted == [position]

    def test_selling_more_than_held_is_refused(self):
        position = SimpleNamespace(quantity=5.0, average_buy_price=200.0, updated_at=None)
        acct = account(1000.0)
        with pytest.raises(service.SettlementError):
            service.settle(
                Fixture(position=position).db,
                proposal(transaction_type="SELL", quantity=50),
                acct,
            )
        assert float(acct.cash_balance) == 1000.0

    def test_selling_something_not_held_is_refused(self):
        with pytest.raises(service.SettlementError):
            service.settle(
                Fixture(position=None).db,
                proposal(transaction_type="SELL", quantity=1),
                account(),
            )


class TestRefusals:
    def test_a_proposal_without_an_amount_is_not_settled(self):
        """Re-pricing here would settle at a figure the user never approved."""
        acct = account()
        with pytest.raises(service.SettlementError):
            service.settle(Fixture().db, proposal(net_amount=None, reference_price=None), acct)
        assert float(acct.cash_balance) == 25000.0

    def test_a_transfer_has_no_settlement_path(self):
        """Banking does not exist. Pretending a transfer settled would be the
        same lie in a new place."""
        with pytest.raises(service.SettlementError) as excinfo:
            service.settle(Fixture().db, proposal(transaction_type="TRANSFER"), account())
        assert "takas" in str(excinfo.value).lower()

    def test_an_unknown_instrument_is_refused(self):
        fix = Fixture(product=None)
        with pytest.raises(service.SettlementError):
            service.settle(fix.db, proposal(), account())

    def test_nothing_is_committed_by_the_service(self):
        """The caller commits once, together with the status flip, so a crash
        cannot move money and leave the proposal pending."""
        fix = Fixture()
        service.settle(fix.db, proposal(), account())
        assert not fix.db.commit.called


class TestPriceFallback:
    def test_a_missing_reference_price_falls_back_to_the_net_per_share(self):
        """Better than booking a zero basis, which would report the whole
        position as pure profit."""
        fix = Fixture(position=None)
        service.settle(fix.db, proposal(quantity=10, net_amount=3000.0, reference_price=None), account())
        assert float(fix.added[0].average_buy_price) == pytest.approx(300.0)

    def test_a_zero_quantity_does_not_divide_by_zero(self):
        fix = Fixture(position=None)
        service.settle(fix.db, proposal(quantity=0, net_amount=0.0, reference_price=None), account())
        assert float(fix.added[0].average_buy_price) == 0.0


class TestEnsureAccount:
    def test_an_existing_account_is_reused(self):
        """Registration is not the only caller; opening a second account for
        the same user would split their cash in two."""
        db = MagicMock(spec=Session)
        existing = SimpleNamespace(id="acct-1", user_id="user-1")
        db.query.return_value.filter.return_value.first.return_value = existing
        assert service.ensure_account(db, "user-1") is existing
        assert not db.add.called

    def test_a_new_account_opens_with_starting_cash(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        account = service.ensure_account(db, "user-2")
        assert account.user_id == "user-2"
        assert float(account.cash_balance) == service.STARTING_CASH
        assert db.add.called

    def test_the_account_number_derives_from_the_user_id(self):
        """Derived rather than counted: two concurrent registrations cannot
        collide on a shared counter."""
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        first = service.ensure_account(db, "aaaaaaaa-1111-2222-3333-444444444444")
        second = service.ensure_account(db, "bbbbbbbb-1111-2222-3333-444444444444")
        assert first.account_number != second.account_number
