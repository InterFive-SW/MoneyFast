"""Market data reads and writes.

Symbol resolution gets the most attention here because getting it wrong is
what made the assistant refuse an ordinary buy order: the user typed "THYAO"
and the system only recognised "TEST-THYAO".

The other recurring theme is that a gap stays a gap. An unknown symbol is not
created, a missing ratio is not zeroed, and an ambiguous name is not guessed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.investment import market_service

NOW = datetime.now(timezone.utc)


def product(symbol="THYAO", data_symbol="THYAO.IS", name="Türk Hava Yolları"):
    return SimpleNamespace(
        id=f"p-{symbol}", symbol=symbol, data_symbol=data_symbol, name=name,
        product_type="stock", market="BIST", currency_code="TRY", status="active",
    )


class Resolver:
    """A Session double whose query chain answers resolve_symbol's three steps
    in order: exact symbol, data_symbol, then name LIKE."""

    def __init__(self, exact=None, by_data=None, by_name=None):
        self.results = [exact, by_data]
        self.by_name = by_name or []
        self.db = MagicMock(spec=Session)
        chain = self.db.query.return_value.filter.return_value
        chain.first.side_effect = self.results
        chain.limit.return_value.all.return_value = self.by_name


class TestSymbolResolution:
    """The bug that made a buy order fail."""

    def test_exact_symbol(self):
        target = product()
        assert market_service.resolve_symbol(Resolver(exact=target).db, "THYAO") is target

    @pytest.mark.parametrize("typed", ["thyao", "Thyao", "THYAO"])
    def test_case_is_ignored(self, typed):
        target = product()
        assert market_service.resolve_symbol(Resolver(exact=target).db, typed) is target

    def test_provider_suffix_is_stripped(self):
        """People paste "THYAO.IS" out of a data provider."""
        target = product()
        assert market_service.resolve_symbol(Resolver(exact=target).db, "THYAO.IS") is target

    def test_the_historical_test_prefix_still_resolves(self):
        """Old links and saved messages carry it; refusing them would be a
        regression for anyone who bookmarked one."""
        target = product()
        assert market_service.resolve_symbol(Resolver(exact=target).db, "TEST-THYAO") is target

    def test_fx_suffix_is_stripped(self):
        target = product("USDTRY", "USDTRY=X", "Dolar")
        assert market_service.resolve_symbol(Resolver(exact=target).db, "USDTRY=X") is target

    def test_falls_back_to_the_provider_symbol(self):
        target = product()
        assert market_service.resolve_symbol(Resolver(by_data=target).db, "SOMETHING") is target

    def test_company_name_resolves_when_unambiguous(self):
        target = product()
        resolver = Resolver(by_name=[target])
        assert market_service.resolve_symbol(resolver.db, "Türk Hava Yolları") is target

    def test_an_ambiguous_name_is_refused_rather_than_guessed(self):
        """Staging a transaction against the wrong instrument is far worse
        than asking which one was meant."""
        resolver = Resolver(by_name=[product("A"), product("B")])
        assert market_service.resolve_symbol(resolver.db, "Holding") is None

    def test_unknown_text_resolves_to_nothing(self):
        assert market_service.resolve_symbol(Resolver().db, "NOTATICKER") is None

    @pytest.mark.parametrize("value", ["", None, "   "])
    def test_empty_input_is_not_a_lookup(self, value):
        db = MagicMock(spec=Session)
        assert market_service.resolve_symbol(db, value) is None


class TestUpsertFundamentals:
    def _db(self, *symbols):
        db = MagicMock(spec=Session)
        db.query.return_value.all.return_value = [product(s) for s in symbols]
        db.execute.return_value = SimpleNamespace(rowcount=len(symbols))
        return db

    def test_rows_are_written(self):
        db = self._db("THYAO")
        assert market_service.upsert_fundamentals(db, [{"symbol": "THYAO", "pe_ratio": 8.2}]) == 1
        assert db.commit.called

    def test_missing_ratio_is_written_as_null_not_zero(self):
        """A company with no published earnings must not screen as the
        cheapest name on the list."""
        db = self._db("THYAO")
        market_service.upsert_fundamentals(db, [{"symbol": "THYAO", "pb_ratio": 1.4}])
        values = db.execute.call_args.args[0].compile().params
        assert values["pe_ratio_m0"] is None

    def test_unknown_symbol_is_skipped(self):
        db = self._db("THYAO")
        assert market_service.upsert_fundamentals(db, [{"symbol": "NOPE"}]) == 0
        assert db.execute.called is False

    def test_empty_batch_makes_no_query(self):
        db = self._db("THYAO")
        assert market_service.upsert_fundamentals(db, []) == 0
        assert db.execute.called is False


class TestListInstruments:
    def _db(self, rows):
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = rows
        db.query.return_value.filter.return_value.first.return_value = product()
        return db

    def _row(self, pe=8.2, pb=1.4, sector="Industrials"):
        quote = SimpleNamespace(
            price=304.0, change_amount=3.0, change_percent=1.0,
            market_timestamp=NOW, received_at=NOW,
        )
        fundamentals = SimpleNamespace(
            pe_ratio=pe, pb_ratio=pb, market_cap=1000, dividend_yield=2.29,
            sector=sector, week52_high=355.5, week52_low=210.0,
        )
        return (product(), quote, fundamentals)

    def test_projects_quote_and_fundamentals_together(self):
        rows = market_service.list_instruments(self._db([self._row()]))
        assert rows[0]["symbol"] == "THYAO"
        assert rows[0]["price"] == 304.0
        assert rows[0]["pe_ratio"] == pytest.approx(8.2)

    def test_instrument_without_fundamentals_still_appears(self):
        """Dropping it would hide the gap rather than report it."""
        quote = SimpleNamespace(price=304.0, change_amount=None, change_percent=None,
                                market_timestamp=NOW, received_at=NOW)
        rows = market_service.list_instruments(self._db([(product(), quote, None)]))
        assert rows[0]["pe_ratio"] is None
        assert rows[0]["price"] == 304.0

    def test_a_pe_filter_excludes_unknown_values(self):
        """"P/E below 10" must not silently mean "P/E below 10, or unknown"."""
        db = self._db([])
        market_service.list_instruments(db, filters={"max_pe": 10})
        sql = str(db.execute.call_args.args[0]).upper()
        assert "IS NOT NULL" in sql

    def test_an_unresolvable_symbol_yields_nothing_not_everything(self):
        """Without the sentinel the IN clause would be empty and the query
        would silently widen to the whole universe."""
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = []
        db.query.return_value.filter.return_value.first.return_value = None
        db.query.return_value.filter.return_value.limit.return_value.all.return_value = []
        assert market_service.list_instruments(db, symbols=["NOPE"]) == []

    @pytest.mark.parametrize("sort_by", ["symbol", "change_percent", "market_cap", "pe_ratio"])
    def test_known_sorts_are_applied(self, sort_by):
        db = self._db([])
        market_service.list_instruments(db, sort_by=sort_by)
        assert "ORDER BY" in str(db.execute.call_args.args[0]).upper()

    def test_limit_is_bounded(self):
        db = self._db([])
        market_service.list_instruments(db, limit=99999)
        assert "LIMIT" in str(db.execute.call_args.args[0]).upper()


class TestHoldings:
    def _db(self, rows):
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = rows
        return db

    def _row(self, price=304.0):
        position = SimpleNamespace(quantity=120, average_buy_price=280.0, opened_at=NOW)
        quote = (
            SimpleNamespace(price=price, previous_close=301.0, change_percent=1.0,
                            market_timestamp=NOW, received_at=NOW)
            if price is not None else None
        )
        return (position, product(), quote)

    def test_joins_position_product_and_quote(self):
        rows = market_service.holdings(self._db([self._row()]))
        assert rows[0]["symbol"] == "THYAO"
        assert rows[0]["quantity"] == 120
        assert rows[0]["price"] == 304.0

    def test_a_holding_with_no_quote_reports_a_null_price(self):
        """Not zero: zero renders as a holding that lost all its value."""
        rows = market_service.holdings(self._db([self._row(price=None)]))
        assert rows[0]["price"] is None
        assert rows[0]["quantity"] == 120

    def test_empty_account_yields_no_rows(self):
        assert market_service.holdings(self._db([])) == []


class TestCandleSeries:
    def test_unknown_product_yields_nothing(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        assert market_service.candle_series(db, "NOPE") == []

    def test_bars_are_returned_oldest_first(self):
        """Charts draw left to right; a reversed series would render the
        history backwards."""
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = product()
        bars = [
            SimpleNamespace(timestamp=NOW, open_price=1, high_price=2, low_price=1,
                            close_price=2, volume=10),
            SimpleNamespace(timestamp=NOW - timedelta(days=1), open_price=3, high_price=4,
                            low_price=3, close_price=4, volume=20),
        ]
        chain = db.query.return_value.filter.return_value.order_by.return_value.limit.return_value
        chain.all.return_value = bars
        series = market_service.candle_series(db, "THYAO")
        assert series[0]["close"] == 4.0
        assert series[1]["close"] == 2.0


class TestBreakdownHelpers:
    def test_sector_map_skips_instruments_without_one(self):
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = [("THYAO", "Industrials")]
        assert market_service.sector_by_symbol(db) == {"THYAO": "Industrials"}

    def test_dividend_rows_leave_dates_blank(self):
        """The provider publishes no ex-date, and a wrong one could have
        someone trade against it."""
        db = MagicMock(spec=Session)
        db.execute.return_value.all.side_effect = [
            [(SimpleNamespace(quantity=1, average_buy_price=1, opened_at=NOW), product(), None)],
            [("THYAO", 2.29, 304.0)],
        ]
        rows = market_service.dividend_rows(db)
        assert rows[0]["exDate"] == ""
        assert rows[0]["yieldPercent"] == pytest.approx(2.29)

    def test_recent_orders_map_status_to_turkish(self):
        db = MagicMock(spec=Session)
        proposal = SimpleNamespace(
            id="PROP-1", symbol="THYAO", status="CONFIRMED", transaction_type="BUY",
            quantity=10, payload={"estimate": {"reference_price": 304.0}}, created_at=NOW,
        )
        db.query.return_value.order_by.return_value.limit.return_value.all.return_value = [proposal]
        rows = market_service.recent_orders(db)
        assert rows[0]["status"] == "Gerçekleşti"
        assert rows[0]["type"] == "Alış"
        assert rows[0]["total"] == pytest.approx(3040.0)

    def test_an_unpriced_proposal_totals_zero_rather_than_raising(self):
        db = MagicMock(spec=Session)
        proposal = SimpleNamespace(
            id="PROP-2", symbol=None, status="REJECTED_VALIDATION", transaction_type="SELL",
            quantity=None, payload={}, created_at=NOW,
        )
        db.query.return_value.order_by.return_value.limit.return_value.all.return_value = [proposal]
        rows = market_service.recent_orders(db)
        assert rows[0]["type"] == "Satış"
        assert rows[0]["total"] == 0.0


class TestAccount:
    def test_looks_up_by_account_number(self):
        db = MagicMock(spec=Session)
        expected = SimpleNamespace(account_number="TR-DEMO-0001")
        db.query.return_value.filter.return_value.first.return_value = expected
        assert market_service.account(db) is expected


class TestSortOrdering:
    """An unrecognised sort is refused rather than quietly ignored.

    The endpoint used to accept any value and fall back to alphabetical, so a
    caller that asked to rank by daily change received symbol order with no
    indication its sort had been dropped — a wrong ranking presented as right.
    """

    def _db(self):
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = []
        return db

    @pytest.mark.parametrize(
        "sort_by", ["symbol", "change_percent", "change_percent_asc", "market_cap", "pe_ratio"]
    )
    def test_every_documented_sort_is_accepted(self, sort_by):
        market_service.list_instruments(self._db(), sort_by=sort_by)

    def test_the_falling_direction_exists(self):
        """"En çok düşenler" was unanswerable while change_percent was
        descending-only."""
        db = self._db()
        market_service.list_instruments(db, sort_by="change_percent_asc")
        sql = str(db.execute.call_args.args[0]).upper()
        assert "ORDER BY" in sql
        assert "ASC" in sql

    def test_the_rising_direction_is_descending(self):
        db = self._db()
        market_service.list_instruments(db, sort_by="change_percent")
        assert "DESC" in str(db.execute.call_args.args[0]).upper()

    def test_an_unknown_sort_is_refused(self):
        with pytest.raises(market_service.UnknownSortError) as excinfo:
            market_service.list_instruments(self._db(), sort_by="gainers")
        assert "gainers" in str(excinfo.value)
        assert "change_percent_asc" in str(excinfo.value)

    def test_no_sort_defaults_to_symbol(self):
        db = self._db()
        market_service.list_instruments(db, sort_by=None)
        assert "ORDER BY" in str(db.execute.call_args.args[0]).upper()


class TestAccountResolution:
    """Cash and holdings are per-user now. A single shared account meant one
    person's purchase spent everybody's money."""

    def test_a_user_gets_their_own_account(self):
        db = MagicMock(spec=Session)
        mine = SimpleNamespace(id="acct-mine")
        db.query.return_value.filter.return_value.first.return_value = mine
        assert market_service.account(db, user_id="user-1") is mine

    def test_an_anonymous_caller_falls_back_to_the_demo_account(self):
        """The public endpoints work without a token and need something to
        read."""
        db = MagicMock(spec=Session)
        demo = SimpleNamespace(id="acct-demo")
        db.query.return_value.filter.return_value.first.return_value = demo
        assert market_service.account(db, user_id=None) is demo

    def test_a_user_without_an_account_falls_back_rather_than_erroring(self):
        db = MagicMock(spec=Session)
        demo = SimpleNamespace(id="acct-demo")
        db.query.return_value.filter.return_value.first.side_effect = [None, demo]
        assert market_service.account(db, user_id="ghost") is demo

    def test_an_explicit_account_number_wins(self):
        db = MagicMock(spec=Session)
        named = SimpleNamespace(id="acct-named")
        db.query.return_value.filter.return_value.first.return_value = named
        assert market_service.account(db, account_number="TR-DEMO-0001") is named

    def test_holdings_for_a_caller_with_no_account_are_empty_not_everyones(self):
        """Without the guard the query would drop its account filter and
        return every position in the database."""
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        assert market_service.holdings(db, user_id="ghost") == []
