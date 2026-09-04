"""What an operator can do to a customer account, and what they cannot.

The rule every action here follows: nothing writes a balance directly. Cash
moves through the banking ledger and positions settle the way a confirmed
order settles, so an adjustment always has a statement line explaining it.
An adjustment nobody can see is how a demo acquires a balance nobody can
account for.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.admin import service


def _account(balance=1000.0, currency="TRY"):
    return SimpleNamespace(
        id="acc-1", account_number="TR-TEST-0001", balance=balance,
        currency_code=currency, status="active", user_id="u-1",
    )


class TestCashAdjustment:
    def test_a_credit_goes_through_the_ledger(self, mocker):
        """Not `UPDATE accounts SET balance`. The customer has to be able to
        see it in their own statement."""
        posted = mocker.patch.object(
            service.banking_service, "post_adjustment",
            return_value={"reference_number": "TRF-1", "balance_after": 3500.0,
                          "currency": "TRY"},
        )
        mocker.patch.object(
            service.banking_service, "deposit_account", return_value=_account(),
        )
        result = service.adjust_cash(
            MagicMock(spec=Session), "u-1", 2500.0, None, actor="admin",
        )
        assert result["balance_after"] == 3500.0
        assert posted.called

    def test_a_customer_with_no_account_is_refused(self, mocker):
        mocker.patch.object(service.banking_service, "deposit_account", return_value=None)
        with pytest.raises(service.AdminActionError):
            service.adjust_cash(MagicMock(spec=Session), "u-1", 100.0, None, actor="admin")

    def test_a_ledger_refusal_surfaces_as_an_admin_error(self, mocker):
        """Over-withdrawing must be reported, not become a negative balance on
        the customer's screen."""
        mocker.patch.object(service.banking_service, "deposit_account", return_value=_account())
        mocker.patch.object(
            service.banking_service, "post_adjustment",
            side_effect=service.banking_service.TransferError("Bakiye eksiye düşemez"),
        )
        with pytest.raises(service.AdminActionError, match="eksiye"):
            service.adjust_cash(MagicMock(spec=Session), "u-1", -99999.0, None, actor="admin")

    def test_the_default_description_names_the_direction(self, mocker):
        mocker.patch.object(service.banking_service, "deposit_account", return_value=_account())
        posted = mocker.patch.object(
            service.banking_service, "post_adjustment",
            return_value={"reference_number": "T", "balance_after": 0.0, "currency": "TRY"},
        )
        service.adjust_cash(MagicMock(spec=Session), "u-1", -50.0, None, actor="admin")
        assert "çekme" in posted.call_args.kwargs["description"]


class TestPositionAdjustment:
    def _wire(self, mocker, *, product=SimpleNamespace(id="p-1", symbol="THYAO"),
              owner=SimpleNamespace(id="ia-1"), position=None, price=300.0):
        import app.modules.investment.market_service as ms

        mocker.patch.object(ms, "resolve_symbol", return_value=product)
        mocker.patch.object(ms, "account", return_value=owner)
        mocker.patch.object(
            ms, "latest_quotes",
            return_value={"THYAO": {"price": price}} if price is not None else {},
        )
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = position
        return db

    def test_granting_opens_a_position_at_the_market_price(self, mocker):
        """A holding handed out at zero cost shows an infinite return on the
        customer's own portfolio screen."""
        db = self._wire(mocker)
        result = service.adjust_position(db, "u-1", "THYAO", 5, actor="admin")
        assert result["quantity_after"] == 5
        assert db.add.called

    def test_granting_with_no_price_is_refused(self, mocker):
        db = self._wire(mocker, price=None)
        with pytest.raises(service.AdminActionError, match="fiyat"):
            service.adjust_position(db, "u-1", "THYAO", 5, actor="admin")

    def test_removing_more_than_is_held_is_refused(self, mocker):
        db = self._wire(mocker, position=SimpleNamespace(
            quantity=3, average_buy_price=250.0,
        ))
        with pytest.raises(service.AdminActionError, match="çıkarılamaz"):
            service.adjust_position(db, "u-1", "THYAO", -99, actor="admin")

    def test_removing_everything_deletes_the_row(self, mocker):
        """A zero-quantity row is a holding the customer does not hold."""
        db = self._wire(mocker, position=SimpleNamespace(quantity=3, average_buy_price=250.0))
        service.adjust_position(db, "u-1", "THYAO", -3, actor="admin")
        assert db.delete.called

    def test_adding_to_a_holding_uses_a_weighted_average(self, mocker):
        """The same rule a confirmed buy applies."""
        position = SimpleNamespace(quantity=10, average_buy_price=200.0)
        db = self._wire(mocker, position=position, price=300.0)
        service.adjust_position(db, "u-1", "THYAO", 10, actor="admin")
        assert position.average_buy_price == pytest.approx(250.0)

    def test_reducing_a_holding_leaves_the_average_cost_alone(self, mocker):
        """Selling part of a position does not change what the rest cost. Only
        a purchase moves the weighted average."""
        position = SimpleNamespace(quantity=10, average_buy_price=200.0)
        db = self._wire(mocker, position=position, price=300.0)
        result = service.adjust_position(db, "u-1", "THYAO", -4, actor="admin")
        assert result["quantity_after"] == 6
        assert position.average_buy_price == 200.0

    def test_zero_is_refused(self, mocker):
        db = self._wire(mocker)
        with pytest.raises(service.AdminActionError):
            service.adjust_position(db, "u-1", "THYAO", 0, actor="admin")

    def test_an_unknown_symbol_is_refused(self, mocker):
        db = self._wire(mocker, product=None)
        with pytest.raises(service.AdminActionError, match="bulunamadı"):
            service.adjust_position(db, "u-1", "nonsense", 1, actor="admin")

    def test_a_customer_with_no_investment_account_is_refused(self, mocker):
        db = self._wire(mocker, owner=None)
        with pytest.raises(service.AdminActionError, match="yatırım"):
            service.adjust_position(db, "u-1", "THYAO", 1, actor="admin")


class TestBills:
    def test_issuing_stores_the_bill(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        bill = service.issue_bill(
            db, institution="BEDAŞ", bill_type="electricity",
            subscriber_no="TEST-1", amount=100.0, due_day=15, actor="admin",
        )
        assert bill.institution == "BEDAŞ" and bill.status == "pending"

    def test_a_second_open_bill_for_the_same_subscriber_is_refused(self):
        """The partial unique index would reject it anyway; a caught duplicate
        reads better than a 500."""
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id="b-1")
        with pytest.raises(service.AdminActionError, match="zaten var"):
            service.issue_bill(
                db, institution="BEDAŞ", bill_type="electricity",
                subscriber_no="TEST-1", amount=100.0, due_day=15, actor="admin",
            )

    def test_withdrawing_an_unpaid_bill_removes_it(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            id="b-1", status="pending",
        )
        assert service.withdraw_bill(db, "b-1") is True

    def test_a_paid_bill_is_history_and_stays(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            id="b-1", status="paid",
        )
        with pytest.raises(service.AdminActionError):
            service.withdraw_bill(db, "b-1")

    def test_withdrawing_a_missing_bill_reports_not_found(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        assert service.withdraw_bill(db, "nope") is False


class TestCustomerOverview:
    """What an operator sees, and what they must NOT see.

    `market_service.holdings` falls back to the shared DEMO portfolio for a
    customer with no investment account. Reading the demo portfolio is
    harmless; showing it under someone's name to an operator who is about to
    act on it is not.
    """

    def _users(self, mocker, *users):
        import app.modules.auth.models as auth_models

        db = MagicMock(spec=Session)
        db.query.return_value.order_by.return_value.all.return_value = list(users)
        mocker.patch.object(auth_models, "User", create=True)
        return db

    def _user(self, tc="11111111110"):
        from datetime import datetime, timezone
        return SimpleNamespace(
            id="u-1", tc_no=tc, email="t@example.com", first_name="Test",
            last_name="Kullanici", is_active=True,
            created_at=datetime.now(timezone.utc),
        )

    def test_a_customer_row_carries_cash_and_portfolio(self, mocker):
        import app.modules.investment.ai_service as ai_service
        import app.modules.investment.market_service as ms

        db = self._users(mocker, self._user())
        mocker.patch.object(service.banking_service, "deposit_account",
                            return_value=_account(1500.0))
        mocker.patch.object(ms, "latest_quotes", return_value={})
        mocker.patch.object(ai_service, "fx_rates", return_value={"TRY": 1.0})
        mocker.patch.object(ms, "account", return_value=SimpleNamespace(id="ia-1"))
        mocker.patch.object(ms, "holdings", return_value=[{"symbol": "THYAO"}])
        mocker.patch.object(ai_service, "holding_value", return_value=900.0)

        row = service.list_customers(db)[0]
        assert row["cash_balance"] == 1500.0
        assert row["portfolio_value"] == 900.0
        assert row["position_count"] == 1

    def test_a_customer_with_no_investment_account_shows_no_holdings(self, mocker):
        """Not the demo portfolio."""
        import app.modules.investment.ai_service as ai_service
        import app.modules.investment.market_service as ms

        db = self._users(mocker, self._user())
        mocker.patch.object(service.banking_service, "deposit_account", return_value=None)
        mocker.patch.object(ms, "latest_quotes", return_value={})
        mocker.patch.object(ai_service, "fx_rates", return_value={"TRY": 1.0})
        mocker.patch.object(ms, "account", return_value=None)
        demo = mocker.patch.object(ms, "holdings", return_value=[{"symbol": "DEMO"}])

        row = service.list_customers(db)[0]
        assert row["position_count"] == 0 and row["portfolio_value"] == 0.0
        assert not demo.called, "holdings() must not be consulted without an account"

    def test_an_unconvertible_holding_is_excluded_not_invented(self, mocker):
        """A holding whose currency has no rate is left out rather than
        counted at 1.0 -- an invented rate is an invented total."""
        import app.modules.investment.ai_service as ai_service
        import app.modules.investment.market_service as ms

        db = self._users(mocker, self._user())
        mocker.patch.object(service.banking_service, "deposit_account",
                            return_value=_account(0.0))
        mocker.patch.object(ms, "latest_quotes", return_value={})
        mocker.patch.object(ai_service, "fx_rates", return_value={"TRY": 1.0})
        mocker.patch.object(ms, "account", return_value=SimpleNamespace(id="ia-1"))
        mocker.patch.object(ms, "holdings", return_value=[{"symbol": "AAPL"}, {"symbol": "THYAO"}])
        mocker.patch.object(ai_service, "holding_value", side_effect=[None, 500.0])

        row = service.list_customers(db)[0]
        assert row["portfolio_value"] == 500.0
        assert row["position_count"] == 2  # held, just not all countable


class TestCashGoesToTheChosenAccount:
    """Which pot the money lands in.

    Without a selector this always took the deposit account, so crediting a
    customer could never reach their investment cash -- that lives in
    `investment_accounts.cash_balance`, and no banking account is it. That is
    exactly the "add money works for banking but not investing" complaint.
    """

    def _investment(self, mocker, cash=1000.0):
        import app.modules.investment.market_service as ms

        owner = SimpleNamespace(
            id="ia-1", account_number="TR-INV", currency_code="TRY", cash_balance=cash,
        )
        mocker.patch.object(ms, "account", return_value=owner)
        return owner

    def test_naming_the_investment_account_credits_investment_cash(self, mocker):
        owner = self._investment(mocker, 1000.0)
        result = service.adjust_cash(
            MagicMock(spec=Session), "u-1", 500.0, None, actor="admin",
            account_id="ia-1",
        )
        assert owner.cash_balance == 1500.0
        assert result["balance_after"] == 1500.0
        # No ledger reference: the investment side has no legs of its own.
        assert result["reference_number"] is None

    def test_the_investment_account_may_be_named_by_number(self, mocker):
        owner = self._investment(mocker, 100.0)
        service.adjust_cash(
            MagicMock(spec=Session), "u-1", -40.0, None, actor="admin",
            account_id="TR-INV",
        )
        assert owner.cash_balance == 60.0

    def test_investment_cash_may_not_go_negative(self, mocker):
        self._investment(mocker, 10.0)
        with pytest.raises(service.AdminActionError, match="eksiye"):
            service.adjust_cash(
                MagicMock(spec=Session), "u-1", -500.0, None, actor="admin",
                account_id="ia-1",
            )

    def test_naming_a_banking_account_credits_that_one(self, mocker):
        import app.modules.investment.market_service as ms

        mocker.patch.object(ms, "account", return_value=None)
        target = _account(200.0)
        target.id = "a-2"
        mocker.patch.object(
            service.banking_service, "accounts_for", return_value=[_account(50.0), target],
        )
        posted = mocker.patch.object(
            service.banking_service, "post_adjustment",
            return_value={"reference_number": "T", "balance_after": 700.0, "currency": "TRY"},
        )
        service.adjust_cash(
            MagicMock(spec=Session), "u-1", 500.0, None, actor="admin", account_id="a-2",
        )
        assert posted.call_args.args[1] is target

    def test_an_unknown_account_is_refused(self, mocker):
        import app.modules.investment.market_service as ms

        mocker.patch.object(ms, "account", return_value=None)
        mocker.patch.object(service.banking_service, "accounts_for", return_value=[])
        with pytest.raises(service.AdminActionError, match="Seçilen hesap"):
            service.adjust_cash(
                MagicMock(spec=Session), "u-1", 1.0, None, actor="admin", account_id="ghost",
            )


class TestBillsCarryNames:
    """A bill belongs to nobody until it is paid -- but "meant for" and
    "settled by" are both knowable, and showing neither left an operator
    staring at a subscriber number that told them nothing."""

    def test_issuing_takes_the_name_from_the_assigned_customer(self, mocker):
        mocker.patch.object(service, "_assigned_customer_name", return_value="Test Kullanici")
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        bill = service.issue_bill(
            db, institution="İGDAŞ", bill_type="internet", subscriber_no="S-1",
            amount=10.0, due_day=5, actor="admin",
        )
        assert bill.holder_name == "Test Kullanici"

    def test_an_explicit_name_wins(self, mocker):
        mocker.patch.object(service, "_assigned_customer_name", return_value="Someone Else")
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        bill = service.issue_bill(
            db, institution="İGDAŞ", bill_type="internet", subscriber_no="S-1",
            amount=10.0, due_day=5, actor="admin", holder_name="Yazılı Ad",
        )
        assert bill.holder_name == "Yazılı Ad"

    def test_the_list_resolves_both_names(self, mocker):
        from app.modules.banking.models import Bill

        mocker.patch.object(service, "_assigned_customer_name", return_value="Atanan Kişi")
        mocker.patch.object(service, "_full_name", return_value="Ödeyen Kişi")
        db = MagicMock(spec=Session)
        db.query.return_value.order_by.return_value.all.return_value = [
            Bill(id="b-1", holder_name="Fatura Sahibi", institution="İGDAŞ",
                 bill_type="internet", subscriber_no="S-1", amount=10, due_day=5,
                 status="paid", paid_by="u-1"),
        ]
        row = service.describe_bills(db)[0]
        assert row["holder_name"] == "Fatura Sahibi"
        assert row["assigned_to"] == "Atanan Kişi"
        assert row["paid_by_name"] == "Ödeyen Kişi"


class TestSubscriptionAssignment:
    """Assigning a subscriber number writes it into the customer's saved
    payees -- one table doing both jobs it was already shaped for."""

    def test_assigning_saves_it_for_the_customer(self, mocker):
        from app.modules.banking import payments

        mocker.patch.object(service, "_full_name", return_value="Test Kullanici")
        saved = mocker.patch.object(payments, "save_payee", return_value=SimpleNamespace(
            id="p-1", label="Ev doğalgaz", institution="İGDAŞ", subscriber_no="S-1",
        ))
        result = service.assign_subscription(
            MagicMock(spec=Session), user_id="u-1", institution="İGDAŞ",
            subscriber_no="S-1", label="Ev doğalgaz",
        )
        assert saved.called and result["full_name"] == "Test Kullanici"

    def test_assigning_to_an_unknown_customer_is_refused(self, mocker):
        mocker.patch.object(service, "_full_name", return_value=None)
        with pytest.raises(service.AdminActionError, match="Kullanıcı bulunamadı"):
            service.assign_subscription(
                MagicMock(spec=Session), user_id="ghost", institution="X",
                subscriber_no="1",
            )

    def test_listing_can_be_scoped_to_one_customer(self, mocker):
        from app.modules.banking.models import SavedPayee

        mocker.patch.object(service, "_full_name", return_value="Test Kullanici")
        db = MagicMock(spec=Session)
        chain = db.query.return_value.filter.return_value.order_by.return_value
        chain.all.return_value = [
            SavedPayee(id="p-1", user_id="u-1", label="Ev", institution="İGDAŞ",
                       subscriber_no="S-1"),
        ]
        rows = service.list_subscriptions(db, "u-1")
        assert rows[0]["subscriber_no"] == "S-1"

    def test_listing_everyone_is_the_default(self, mocker):
        mocker.patch.object(service, "_full_name", return_value=None)
        db = MagicMock(spec=Session)
        db.query.return_value.order_by.return_value.all.return_value = []
        assert service.list_subscriptions(db) == []


class TestNameResolution:
    """`_full_name` is what turns a user id into something an operator can
    read. Every branch matters because a blank name in the bill list is the
    complaint this whole change answers."""

    def _db(self, user):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = user
        return db

    def test_first_and_last_name(self):
        user = SimpleNamespace(first_name="Test", last_name="Kullanici", email="t@x.com")
        assert service._full_name(self._db(user), "u-1") == "Test Kullanici"

    def test_a_nameless_user_falls_back_to_their_email(self):
        user = SimpleNamespace(first_name=None, last_name=None, email="t@x.com")
        assert service._full_name(self._db(user), "u-1") == "t@x.com"

    def test_no_user_id_is_no_name(self):
        assert service._full_name(MagicMock(spec=Session), None) is None

    def test_an_unknown_user_is_no_name(self):
        assert service._full_name(self._db(None), "ghost") is None


class TestUnresolvedInstrumentMessage:
    """The staging blocker used to blame the price for a name that was never
    recognised: "Fiyat bilgisi bulunamayan enstrüman: aple"."""

    def _stage(self, **over):
        from app.modules.investment import ai_service

        request = {
            "user_id": "u-1", "transaction_type": "BUY", "idempotency_key": "k",
            "instrument": {"symbol": over.pop("symbol", "aple")}, "quantity": 1,
        }
        return ai_service.stage_transaction(request, **over)

    def test_it_names_the_instrument_not_the_price(self):
        blockers = self._stage()["blockers"]
        assert any("enstrüman bulunamadı" in b for b in blockers)
        assert not any("Fiyat bilgisi" in b for b in blockers)

    def test_it_offers_what_was_probably_meant(self):
        blockers = self._stage(symbol_suggestions=["AAPL"])["blockers"]
        assert any("AAPL mı demek istediniz" in b for b in blockers)

    def test_several_candidates_read_as_a_sentence(self):
        """"A, B veya C" -- not "A veya B veya C", which reads like a machine
        listing rather than a question."""
        blockers = self._stage(symbol_suggestions=["AAPL", "ALAB", "AXON"])["blockers"]
        assert any("AAPL, ALAB veya AXON" in b for b in blockers)

    def test_a_resolved_symbol_with_no_price_still_blames_the_price(self):
        """That message is correct when the instrument DOES exist."""
        blockers = self._stage(resolved_symbol="THYAO")["blockers"]
        assert any("Fiyat bilgisi bulunamayan" in b for b in blockers)
