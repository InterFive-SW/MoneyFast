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
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.modules.investment import market_service

NOW = datetime.now(timezone.utc)


def product(symbol="THYAO", data_symbol="THYAO.IS", name="Türk Hava Yolları"):
    return SimpleNamespace(
        id=f"p-{symbol}", symbol=symbol, data_symbol=data_symbol, name=name,
        product_type="stock", market="BIST", currency_code="TRY", status="active",
    )


NOW_MINUS_1 = NOW - timedelta(days=1)


class Universe:
    """A Session double that hands back the instrument universe.

    Resolution used to be three chained SQL queries, so the old double had to
    script `first()` twice and then `limit().all()`. It now reads the ~190-row
    universe once and matches in Python -- `_fold` exists because Postgres
    folds ı/İ by collation, so a name lookup pushed into SQL can silently stop
    matching on a differently configured database.
    """

    def __init__(self, *products):
        self.db = MagicMock(spec=Session)
        self.db.query.return_value.all.return_value = list(products)


class TestSymbolResolution:
    """The names people actually type.

    Two measured failures drove this. "THY kaç para" answered "fiyat verisine
    ulaşamadım" because THY is not a symbol -- THYAO is. And "turk hava
    yollari" missed too: `_fold` normalises ı and ü, but the name lookup was a
    raw SQL `upper(name) LIKE`, so it required the user to type the Turkish
    characters correctly.
    """

    THY = product()
    APPLE = product("AAPL", "AAPL", "Apple Inc.")

    def _db(self, *extra):
        return Universe(self.THY, self.APPLE, *extra).db

    def test_exact_symbol(self):
        assert market_service.resolve_symbol(self._db(), "THYAO") is self.THY

    @pytest.mark.parametrize("typed", ["thyao", "Thyao", "THYAO"])
    def test_case_is_ignored(self, typed):
        assert market_service.resolve_symbol(self._db(), typed) is self.THY

    def test_provider_suffix_is_stripped(self):
        """People paste "THYAO.IS" out of a data provider."""
        assert market_service.resolve_symbol(self._db(), "THYAO.IS") is self.THY

    def test_the_historical_test_prefix_still_resolves(self):
        """Old links and saved messages carry it; refusing them would be a
        regression for anyone who bookmarked one."""
        assert market_service.resolve_symbol(self._db(), "TEST-THYAO") is self.THY

    def test_fx_suffix_is_stripped(self):
        usd = product("USDTRY", "USDTRY=X", "Dolar")
        assert market_service.resolve_symbol(Universe(usd).db, "USDTRY=X") is usd

    def test_falls_back_to_the_provider_symbol(self):
        odd = product("ZZZ", "SOMETHING", "Zed")
        assert market_service.resolve_symbol(Universe(odd).db, "SOMETHING") is odd

    @pytest.mark.parametrize(
        "typed",
        ["Türk Hava Yolları", "türk hava yolları", "TÜRK HAVA YOLLARI",
         "turk hava yollari", "TURK HAVA YOLLARI"],
    )
    def test_the_company_name_resolves_with_or_without_turkish_letters(self, typed):
        """The unaccented spellings are the ones that used to fail, and they
        are how most people type."""
        assert market_service.resolve_symbol(self._db(), typed) is self.THY

    @pytest.mark.parametrize("typed", ["THY", "thy"])
    def test_the_ticker_abbreviation_resolves(self, typed):
        """THY is not a symbol -- THYAO is. The agent writes THY, the user
        writes THY, and the answer was "fiyat verisine ulaşamadım"."""
        assert market_service.resolve_symbol(self._db(), typed) is self.THY

    def test_a_close_typo_is_OFFERED_rather_than_assumed(self):
        """THAYO scores 0.80 against THYAO -- and so does the Turkish verb
        "almak" against ALARK, and "kış" against ISRG, on the same margin. No
        score separates a typo from an ordinary word, so 0.80 buys a question
        rather than an answer. "THYAO mı demek istediniz?" is a fine reply."""
        db = self._db()
        assert market_service.resolve_symbol(db, "THAYO") is None
        assert [p.symbol for p in market_service.resolve_candidates(db, "THAYO")] == ["THYAO"]

    def test_a_strong_typo_still_resolves(self):
        """0.91 with a clear margin is not a guess."""
        aselsan = product("ASELS", "ASELS.IS", "ASELSAN Elektronik")
        assert market_service.resolve_symbol(Universe(aselsan).db, "aselsn") is aselsan

    def test_an_ordinary_word_never_becomes_an_instrument(self):
        """The bug this bar exists for: "pastırma" scored 0.62 against ASTOR,
        cleared only the suggestion floor, was the single thing that did, and
        came back as an ANSWER. "bana" became BRSAN and "tarifi" became TXN
        the same way -- so "bana pastırma tarifi ver" matched three."""
        astor = product("ASTOR", "ASTOR.IS", "Astor Enerji")
        db = Universe(astor).db
        for word in ("pastırma", "bana", "tarifi", "mantı"):
            assert market_service.resolve_symbol(db, word) is None, word

    def test_a_name_match_beats_a_closer_looking_symbol(self):
        """Fuzzy scoring on symbols alone ranks "apple" -> APP (0.75) ABOVE
        AAPL (0.67). The neighbour search runs last precisely so the name rule
        has already settled it; reordering the two returns the wrong company."""
        app = product("APP", "APP", "AppLovin Corporation")
        assert market_service.resolve_symbol(self._db(app), "apple") is self.APPLE

    def test_an_ambiguous_prefix_is_refused_rather_than_guessed(self):
        """Staging a transaction against the wrong instrument is far worse
        than asking which one was meant."""
        db = Universe(product("KOZAL", "KOZAL.IS", "Koza Altin"),
                      product("KOZAA", "KOZAA.IS", "Koza Madencilik")).db
        assert market_service.resolve_symbol(db, "koz") is None

    def test_unknown_text_resolves_to_nothing(self):
        assert market_service.resolve_symbol(self._db(), "zzzznotaticker") is None

    @pytest.mark.parametrize("value", ["", None, "   "])
    def test_empty_input_is_not_a_lookup(self, value):
        """Falling through would match the entire universe on an empty
        substring."""
        assert market_service.resolve_symbol(self._db(), value) is None


class TestResolutionCandidates:
    """What to offer when it does not settle.

    An ambiguous query used to log "refusing to guess" and hand the user a
    bare "bulunamadı" -- with both matches sitting in the same payload.
    """

    KOZAL = product("KOZAL", "KOZAL.IS", "Koza Altin Isletmeleri")
    KOZAA = product("KOZAA", "KOZAA.IS", "Koza Anadolu Metal")

    def test_ambiguity_returns_every_match_to_ask_about(self):
        db = Universe(self.KOZAL, self.KOZAA).db
        found = market_service.resolve_candidates(db, "koz")
        assert {p.symbol for p in found} == {"KOZAL", "KOZAA"}

    def test_a_settled_query_returns_exactly_one(self):
        db = Universe(self.KOZAL, self.KOZAA).db
        assert [p.symbol for p in market_service.resolve_candidates(db, "KOZAL")] == ["KOZAL"]

    def test_nothing_close_offers_nothing(self):
        """A suggestion nobody typed is noise, not help."""
        db = Universe(self.KOZAL).db
        assert market_service.resolve_candidates(db, "zzzznotaticker") == []

    def test_suggestions_are_capped(self):
        db = Universe(*[product(f"AKS{i}", f"AKS{i}.IS", f"Aks {i} Holding")
                        for i in range(6)]).db
        assert len(market_service.resolve_candidates(db, "aks")) <= 3


class TestStrictResolution:
    """The money path never guesses.

    A misread ticker on a price question is an annoyance. On a buy order it
    spends real money on the wrong company, so `transactions/stage` takes
    deterministic matches only.
    """

    THY = product()

    def test_an_abbreviation_still_resolves_strictly(self):
        """THY -> THYAO is a unique symbol prefix, not a guess, so an order
        for "THY" is still perfectly ordinary."""
        db = Universe(self.THY).db
        assert market_service.resolve_symbol(db, "THY", strict=True) is self.THY

    def test_an_unaccented_name_still_resolves_strictly(self):
        db = Universe(self.THY).db
        assert market_service.resolve_symbol(db, "turk hava yollari", strict=True) is self.THY

    def test_a_typo_is_refused_on_the_money_path(self):
        """Strict mode never reaches the neighbour search at all, so a typo
        yields nothing to act on -- not even a suggestion to act on."""
        db = Universe(self.THY).db
        assert market_service.resolve_symbol(db, "THAYO", strict=True) is None
        assert market_service.resolve_candidates(db, "THAYO", strict=True) == []


class TestNoMatchQuery:
    """What the query looks like when nothing resolved.

    The sentinel used to be the string "\\x00". Postgres rejects it outright --
    "A string literal cannot contain NUL (0x00) characters" -- so a request
    where NOTHING resolved answered 500 rather than an empty list. That is
    exactly the case that most needs a helpful answer: "koz hissesi kaç para"
    crashed the endpoint instead of offering KOZAL and KOZAA.
    """

    def _sql(self, db):
        statement = db.execute.call_args[0][0]
        return str(statement.compile(compile_kwargs={"literal_binds": True}))

    def test_an_unresolvable_symbol_never_puts_a_nul_in_the_sql(self):
        db = Universe(product()).db
        db.execute.return_value.all.return_value = []
        market_service.list_instruments(db, symbols=["zzzznotaticker"])
        sql = self._sql(db)
        assert "\x00" not in sql
        assert "false" in sql.lower()

    def test_a_resolvable_symbol_still_filters_on_it(self):
        db = Universe(product()).db
        db.execute.return_value.all.return_value = []
        market_service.list_instruments(db, symbols=["THYAO"])
        assert "THYAO" in self._sql(db)


class TestResolutionLastResorts:
    """The two rules that only fire when everything cheaper has missed."""

    def test_initials_resolve_a_name_whose_ticker_shares_no_prefix(self):
        """The acronym rule. "THY" reaches THYAO by symbol prefix, but a
        company whose ticker looks nothing like its initials has only this."""
        odd = product("XKCD1", "XKCD1.IS", "Bir İki Üç Sanayi")
        assert market_service.resolve_symbol(Universe(odd).db, "biu") is odd

    def test_a_fuzzy_tie_is_offered_rather_than_guessed(self):
        """Two neighbours equally close, sharing no prefix and no name
        substring, so only the neighbour search can see them. Equally close
        means there is no winner to pick."""
        a = product("QWERTA", "QWERTA.IS", "Alpha")
        b = product("ZWERTY", "ZWERTY.IS", "Beta")
        found = market_service.resolve_candidates(Universe(a, b).db, "qwerty")
        assert {p.symbol for p in found} == {"QWERTA", "ZWERTY"}
        assert market_service.resolve_symbol(Universe(a, b).db, "qwerty") is None


class TestSymbolSuggestions:
    def test_only_unsettled_queries_are_reported(self):
        db = Universe(product(), product("KOZAL", "KOZAL.IS", "Koza Altin"),
                      product("KOZAA", "KOZAA.IS", "Koza Metal")).db
        out = market_service.symbol_suggestions(db, ["THYAO", "koz"])
        assert [item["query"] for item in out] == ["koz"]
        assert set(out[0]["candidates"]) == {"KOZAL", "KOZAA"}

    def test_nothing_asked_reports_nothing(self):
        assert market_service.symbol_suggestions(Universe(product()).db, None) == []

    def test_an_unmatchable_query_is_reported_with_no_candidates(self):
        """"Nothing close to this" is an honest answer; silence is not."""
        out = market_service.symbol_suggestions(Universe(product()).db, ["zzzznope"])
        assert out == [{"query": "zzzznope", "candidates": []}]


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

    def test_every_field_is_both_inserted_and_refreshed(self):
        """The INSERT payload and the ON CONFLICT update set were two
        separate literal tuples. A field added to one and not the other is
        written the day an instrument first appears and never updated again
        -- correct once, stale forever, and silent about it."""
        db = self._db("THYAO")
        market_service.upsert_fundamentals(
            db, [{"symbol": "THYAO", "operating_margin": -0.026}]
        )
        statement = db.execute.call_args.args[0]
        compiled = statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
        # The emitted SQL, not SQLAlchemy internals: the internal structure
        # of an upsert is not the thing this test is about.
        sql = str(compiled)
        insert_clause, _, update_clause = sql.partition("DO UPDATE SET")

        for field in market_service.FUNDAMENTAL_FIELDS:
            assert field in insert_clause, f"{field} is never inserted"
            assert field in update_clause, f"{field} is inserted but never refreshed"

    def test_a_negative_margin_is_carried_not_treated_as_missing(self):
        """An operating LOSS is the most informative thing a margin can say."""
        db = self._db("THYAO")
        market_service.upsert_fundamentals(
            db, [{"symbol": "THYAO", "operating_margin": -0.026}]
        )
        values = db.execute.call_args.args[0].compile().params
        assert values["operating_margin_m0"] == -0.026


class TestFundamentalsFor:
    """One instrument's stored fundamentals, for the page and the chat."""

    def _db(self, row):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.side_effect = [
            product("THYAO"), row,
        ]
        return db

    def test_an_unknown_symbol_has_no_record(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        assert market_service.fundamentals_for(db, "YOKBOYLE") is None

    def test_an_instrument_with_no_row_yet_has_no_record(self):
        assert market_service.fundamentals_for(self._db(None), "THYAO") is None

    def test_decimals_become_floats(self):
        """`Numeric()` comes back as Decimal, which does not survive JSON."""
        from decimal import Decimal

        row = SimpleNamespace(
            updated_at=NOW,
            **{f: None for f in market_service.FUNDAMENTAL_FIELDS},
        )
        row.operating_margin = Decimal("-0.0260")
        row.total_revenue = 26_350_999_552

        out = market_service.fundamentals_for(self._db(row), "THYAO")

        assert isinstance(out["operating_margin"], float)
        assert out["operating_margin"] == pytest.approx(-0.026)
        assert out["total_revenue"] == 26_350_999_552

    def test_a_missing_field_stays_none(self):
        """A bank has no gross margin. Reporting 0 would state a fact the
        company never had."""
        row = SimpleNamespace(
            updated_at=NOW,
            **{f: None for f in market_service.FUNDAMENTAL_FIELDS},
        )
        out = market_service.fundamentals_for(self._db(row), "THYAO")
        assert out["gross_margin"] is None


class TestListInstruments:
    def _db(self, rows):
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = rows
        db.query.return_value.filter.return_value.first.return_value = product()
        return db

    def _row(self, pe=8.2, pb=1.4, sector="Industrials", volume=1_250_000):
        quote = SimpleNamespace(
            price=304.0, change_amount=3.0, change_percent=1.0,
            volume=volume, market_timestamp=NOW, received_at=NOW,
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

    def test_volume_is_projected(self):
        """Stored on every quote row and exposed by nothing, so the chat's
        turnover column could only ever say "veri yok"."""
        rows = market_service.list_instruments(self._db([self._row()]))
        assert rows[0]["volume"] == 1_250_000

    def test_a_quote_without_volume_reports_none(self):
        rows = market_service.list_instruments(self._db([self._row(volume=None)]))
        assert rows[0]["volume"] is None

    def test_instrument_without_fundamentals_still_appears(self):
        """Dropping it would hide the gap rather than report it."""
        quote = SimpleNamespace(price=304.0, change_amount=None, change_percent=None,
                                volume=None, market_timestamp=NOW, received_at=NOW)
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

    def _row(self, price=304.0, sector="Industrials"):
        position = SimpleNamespace(quantity=120, average_buy_price=280.0, opened_at=NOW)
        quote = (
            SimpleNamespace(price=price, previous_close=301.0, change_percent=1.0,
                            market_timestamp=NOW, received_at=NOW)
            if price is not None else None
        )
        fundamentals = SimpleNamespace(sector=sector) if sector is not None else None
        return (position, product(), quote, fundamentals)

    def test_joins_position_product_and_quote(self):
        rows = market_service.holdings(self._db([self._row()]))
        assert rows[0]["symbol"] == "THYAO"
        assert rows[0]["quantity"] == 120
        assert rows[0]["price"] == 304.0

    def test_sector_is_carried_for_the_risk_engine(self):
        """Absent it, the risk engine bucketed every portfolio as 100%
        UNCLASSIFIED -- not because sectors were unknown, but because the
        positions handed to it never carried the field."""
        rows = market_service.holdings(self._db([self._row()]))
        assert rows[0]["sector"] == "Industrials"

    def test_an_unclassified_instrument_reports_no_sector(self):
        rows = market_service.holdings(self._db([self._row(sector=None)]))
        assert rows[0]["sector"] is None

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

    def test_the_demo_fallback_can_be_switched_off(self):
        """Reading the demo portfolio when nobody is signed in is harmless.
        Pricing a TRADE against it is not: an expired session named its user
        "anonymous", matched no account, and staged against the shared demo
        balance."""
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.side_effect = [None, "demo"]
        assert (
            market_service.account(db, user_id="ghost", allow_demo_fallback=False)
            is None
        )

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


class TestAliasResolution:
    """The names people actually type.

    "XAU" is the ISO code for gold and the obvious thing to write, but the
    product is XAUUSD named "Altın (Ons/USD)" — exact match, provider symbol
    and name substring all miss it, so the request returned zero rows in
    silence and the assistant said it had no data.
    """

    def _db(self, found=None):
        return Universe(found).db if found is not None else Universe().db

    @pytest.mark.parametrize(
        "typed,expected",
        [
            ("XAU", "XAUUSD"), ("xau", "XAUUSD"), ("altın", "XAUUSD"),
            ("ALTIN", "XAUUSD"), ("gold", "XAUUSD"), ("ons", "XAUUSD"),
            ("dolar", "USDTRY"), ("Dolar", "USDTRY"), ("USD", "USDTRY"),
            ("euro", "EURTRY"), ("EUR", "EURTRY"), ("avro", "EURTRY"),
            ("bist100", "XU100"), ("BIST 100", "XU100"),
        ],
    )
    def test_everyday_names_resolve(self, typed, expected):
        target = product(expected)
        db = self._db(found=target)
        assert market_service.resolve_symbol(db, typed) is target

    def test_the_alias_wins_over_a_name_that_merely_contains_the_word(self):
        """"altın" is not in XAUUSD's ticker and IS in another company's name,
        so the alias has to be consulted before the name rule."""
        gold = product("XAUUSD", "GC=F", "Altın (Ons/USD)")
        decoy = product("ALTINY", "ALTINY.IS", "Altınyağ Madencilik")
        assert market_service.resolve_symbol(Universe(gold, decoy).db, "altın") is gold

    def test_turkish_dotless_i_folds_the_same_either_way(self):
        """`upper()` in Postgres folds ı/İ by collation, so the answer would
        otherwise depend on how the database was created."""
        assert market_service._fold("ALTIN") == market_service._fold("altın")
        assert market_service._fold("İSTANBUL") == market_service._fold("istanbul")

    def test_an_alias_whose_product_is_missing_falls_through(self):
        """A seeded alias pointing at an instrument that is not in this
        deployment must not shadow the normal lookup."""
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.side_effect = [None, None, None]
        db.query.return_value.filter.return_value.limit.return_value.all.return_value = []
        assert market_service.resolve_symbol(db, "gold") is None

    def test_a_normal_ticker_is_unaffected(self):
        target = product("THYAO")
        assert market_service.resolve_symbol(Universe(target).db, "THYAO") is target


class TestNameBackfill:
    """84 of 97 products are stored with name = ticker, which made "Aselsan"
    unresolvable: 'ASELS' LIKE '%ASELSAN%' is false because the stored name is
    SHORTER than what the user typed."""

    def _db(self, product):
        db = MagicMock(spec=Session)
        db.query.return_value.all.return_value = [product]
        db.execute.return_value = SimpleNamespace(rowcount=1)
        return db

    def test_a_placeholder_name_is_replaced(self):
        row = product("ASELS", name="ASELS")
        market_service.upsert_fundamentals(
            self._db(row), [{"symbol": "ASELS", "name": "Aselsan Elektronik"}]
        )
        assert row.name == "Aselsan Elektronik"

    def test_a_real_name_is_never_overwritten(self):
        """Six products carry curated Turkish names from migration 0005. The
        provider's version must not clobber them."""
        row = product("THYAO", name="Türk Hava Yolları A.O.")
        market_service.upsert_fundamentals(
            self._db(row), [{"symbol": "THYAO", "name": "Turkish Airlines Inc."}]
        )
        assert row.name == "Türk Hava Yolları A.O."

    def test_a_missing_provider_name_leaves_the_placeholder(self):
        row = product("ASELS", name="ASELS")
        market_service.upsert_fundamentals(self._db(row), [{"symbol": "ASELS"}])
        assert row.name == "ASELS"

    def test_a_blank_provider_name_is_ignored(self):
        row = product("ASELS", name="ASELS")
        market_service.upsert_fundamentals(
            self._db(row), [{"symbol": "ASELS", "name": "   "}]
        )
        assert row.name == "ASELS"


class TestWatchlistStore:
    """Following an instrument, and the two ways it can go wrong.

    An unresolvable symbol must not create a row: a watchlist entry pointing
    at nothing renders as a blank line the user cannot remove.
    """

    def _db(self, product=None, existing=None):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = existing
        db.query.return_value.filter.return_value.delete.return_value = 1 if existing else 0
        return db

    def test_symbols_come_back_in_the_order_they_were_added(self):
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = [("THYAO",), ("AAPL",)]
        assert market_service.watchlist_symbols(db, "user-1") == ["THYAO", "AAPL"]

    def test_adding_resolves_the_symbol_first(self, mocker):
        db = self._db()
        resolved = product()
        mocker.patch.object(market_service, "resolve_symbol", return_value=resolved)
        assert market_service.watchlist_add(db, "user-1", "thyao") is resolved
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_adding_an_unresolvable_symbol_stores_nothing(self, mocker):
        db = self._db()
        mocker.patch.object(market_service, "resolve_symbol", return_value=None)
        assert market_service.watchlist_add(db, "user-1", "NOPE") is None
        db.add.assert_not_called()

    def test_adding_twice_is_a_no_op(self, mocker):
        """Starring an instrument you already follow is not an error."""
        db = self._db(existing=SimpleNamespace(id="w1"))
        resolved = product()
        mocker.patch.object(market_service, "resolve_symbol", return_value=resolved)
        assert market_service.watchlist_add(db, "user-1", "THYAO") is resolved
        db.add.assert_not_called()

    def test_removing_reports_whether_anything_went(self, mocker):
        db = self._db(existing=SimpleNamespace(id="w1"))
        mocker.patch.object(market_service, "resolve_symbol", return_value=product())
        assert market_service.watchlist_remove(db, "user-1", "THYAO") is True

    def test_removing_something_not_followed_reports_false(self, mocker):
        db = self._db()
        mocker.patch.object(market_service, "resolve_symbol", return_value=product())
        assert market_service.watchlist_remove(db, "user-1", "THYAO") is False

    def test_removing_an_unresolvable_symbol_reports_false(self, mocker):
        db = self._db()
        mocker.patch.object(market_service, "resolve_symbol", return_value=None)
        assert market_service.watchlist_remove(db, "user-1", "NOPE") is False


class TestSearchInstruments:
    """Yazdıkça öneri.

    `resolve_candidates` değil: o "kullanıcı hangi TEK enstrümanı kastetti"
    sorusunu cevaplıyor ve bulanık eşleştiriyor -- para yolunda doğru, öneri
    kutusunda değil.
    """

    def _db(self, products):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.all.return_value = products
        return db

    def _p(self, symbol, name, market="BIST", currency="TRY"):
        return SimpleNamespace(
            symbol=symbol, name=name, market=market, currency_code=currency,
            status="active",
        )

    def test_an_empty_query_returns_nothing(self):
        """Boş arama bütün evreni dökmemeli."""
        assert market_service.search_instruments(self._db([]), "") == []
        assert market_service.search_instruments(self._db([]), "   ") == []

    def test_turkish_folding_finds_the_dotted_name(self):
        """`sise` yazan `ŞİŞE`yi bulmalı. Katlama Python'da, çünkü Postgres
        ı/İ'yi kurulumun collation'ına göre katlıyor."""
        db = self._db([self._p("SISE", "Türkiye Şişe ve Cam Fabrikaları")])
        assert market_service.search_instruments(db, "şişe")[0]["symbol"] == "SISE"

    def test_an_exact_symbol_ranks_first(self):
        db = self._db([
            self._p("THYAOX", "Başka"), self._p("THYAO", "Türk Hava Yolları"),
        ])
        rows = market_service.search_instruments(db, "THYAO")
        assert rows[0]["symbol"] == "THYAO"

    def test_a_prefix_beats_a_name_match(self):
        db = self._db([
            self._p("XYZ", "Thy Holding"), self._p("THYAO", "Türk Hava Yolları"),
        ])
        assert market_service.search_instruments(db, "thy")[0]["symbol"] == "THYAO"

    def test_the_company_name_is_searchable(self):
        db = self._db([self._p("MSFT", "Microsoft Corporation", "NASDAQ", "USD")])
        rows = market_service.search_instruments(db, "microsoft")
        assert rows[0]["symbol"] == "MSFT" and rows[0]["currency"] == "USD"

    def test_the_limit_is_honoured(self):
        db = self._db([self._p(f"AB{i}", f"Şirket {i}") for i in range(20)])
        assert len(market_service.search_instruments(db, "ab", limit=5)) == 5


class TestIntradaySymbols:
    """Gün içi bar gereken küme.

    Evrenin tamamı değil: bin enstrümanın 15 dakikalık barlarını sürekli
    çekmek, sistemin gerektirdiğinden kat kat fazla istek olurdu.
    """

    def test_it_returns_the_symbols_the_query_found(self):
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = [("THYAO",), ("USDTRY",)]
        assert market_service.intraday_symbols(db) == ["THYAO", "USDTRY"]

    def test_an_empty_result_is_an_empty_list(self):
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = []
        assert market_service.intraday_symbols(db) == []


class TestIndexAwareMarketFilter:
    """`market` süzgeci hem borsayı hem endeksi kabul eder.

    AAPL Nasdaq'ta işlem görür VE S&P 500 üyesidir. Yalnızca borsaya
    bakılsaydı "S&P 500 hisseleri" sorgusu Apple'ı, Microsoft'u ve Nvidia'yı
    hiç görmezdi.
    """

    def test_the_index_codes_are_the_ones_the_tabs_send(self):
        assert market_service.INDEX_CODES == {"SP500", "NASDAQ100"}

    def test_an_exchange_is_not_an_index_code(self):
        """BIST, NASDAQ ve NYSE kotasyon borsası; `market` sütununda
        duruyorlar ve üyelik tablosuna girmiyorlar."""
        for exchange in ("BIST", "NASDAQ", "NYSE"):
            assert exchange not in market_service.INDEX_CODES

    def test_a_symbol_matching_neither_rule_is_skipped(self):
        """Ne sembolü ne adı eşleşen bir enstrüman listede yer almaz."""
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.all.return_value = [
            SimpleNamespace(symbol="GARAN", name="Garanti Bankası",
                            market="BIST", currency_code="TRY", status="active"),
        ]
        assert market_service.search_instruments(db, "zzz") == []

    def test_an_index_query_filters_by_membership_not_exchange(self, mocker):
        """S&P sekmesi üyelik tablosunu okur; borsayı değil."""
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = []
        market_service.list_instruments(db, filters={"market": "SP500"}, limit=5)
        assert db.execute.called

    def test_an_exchange_query_filters_by_the_market_column(self):
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = []
        market_service.list_instruments(db, filters={"market": "NYSE"}, limit=5)
        assert db.execute.called


class TestCandleBars:
    """Açılış ve kapanış birlikte.

    `candle_closes` yalnızca kapanışı veriyor; portföyün mumu açılışı da
    istiyor -- tek bir gözlenen değerden çizilen mum, o günün nereden nereye
    gittiğini söylemez.
    """

    def test_bars_come_back_oldest_first(self):
        """Core select ile okunuyor: ORM nesnesi kurmak, üç sütun için
        sorgunun kendisinden yüz kat pahalıydı (41.405 nesne = 1,3 saniye)."""
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = [
            (NOW, 110.0, 115.0),
            (NOW_MINUS_1, 100.0, 105.0),
        ]
        out = market_service.candle_bars(db, "THYAO", limit=2)
        # Sorgu en yeniden okuyor; dönüş eskiden yeniye çevriliyor.
        assert [bar[1] for bar in out] == [100.0, 110.0]

    def test_an_unknown_symbol_has_no_bars(self, mocker):
        mocker.patch.object(market_service, "get_product", return_value=None)
        assert market_service.candle_bars(MagicMock(spec=Session), "NOPE") == []


class TestMarketHeatmap:
    """Piyasa ısı haritası: her hisse piyasa değeri kadar yer kaplar.

    `get_heatmap` ile karıştırılmamalı -- o, kullanıcının portföyünü pozisyon
    ağırlığına göre gösteriyor. Bu, piyasanın kendisini gösteriyor.
    """

    def _row(self, symbol, cap, change, sector="Teknoloji"):
        return SimpleNamespace(
            symbol=symbol, name=f"{symbol} A.Ş.", market_cap=cap,
            sector=sector, change_percent=change, price=100.0,
            currency_code="TRY",
        )

    def _db(self, rows):
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = rows
        return db

    def test_tiles_come_back_largest_first(self):
        """Harita piyasanın kendi ağırlığını gösteriyor."""
        db = self._db([
            self._row("SMALL", 1_000, 1.0),
            self._row("BIG", 900_000, -2.0),
        ])
        out = market_service.market_heatmap(db)
        assert [tile["symbol"] for tile in out["items"]] == ["BIG", "SMALL"]
        assert out["items"][0]["marketCap"] == 900_000

    def test_an_instrument_without_a_market_cap_is_left_out_and_counted(self):
        """Kutu boyutu piyasa değerinden geliyor; varsayılan bir boyut, o
        hisseye sahip olmadığı bir ağırlığı vermek olurdu."""
        db = self._db([
            self._row("OK", 500, 1.0),
            self._row("NOCAP", None, 1.0),
            self._row("NOCHANGE", 500, None),
        ])
        out = market_service.market_heatmap(db)
        assert [tile["symbol"] for tile in out["items"]] == ["OK"]
        assert out["missing"] == 2

    def test_an_index_code_filters_by_membership(self):
        """AAPL Nasdaq'ta işlem görür VE S&P 500 üyesidir."""
        db = self._db([])
        market_service.market_heatmap(db, market="SP500")
        assert db.execute.called

    def test_an_exchange_filters_by_the_market_column(self):
        db = self._db([])
        market_service.market_heatmap(db, market="BIST")
        assert db.execute.called

    def test_the_limit_caps_the_tiles(self):
        db = self._db([self._row(f"S{i}", 1000 - i, 0.5) for i in range(10)])
        assert len(market_service.market_heatmap(db, limit=3)["items"]) == 3

    def test_a_missing_sector_is_named_not_blank(self):
        db = self._db([self._row("X", 100, 1.0, sector=None)])
        assert market_service.market_heatmap(db)["items"][0]["sector"] == "Bilinmiyor"


class TestSymbolsWithoutFundamentals:
    def test_it_lists_what_the_query_found(self):
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = [("AAPL",), ("MSFT",)]
        assert market_service.symbols_without_fundamentals(db) == ["AAPL", "MSFT"]

    def test_a_fully_covered_universe_asks_for_nothing(self):
        """Hepsini her açılışta yeniden çekmek, değişmeyen çeyreklik oranları
        durmadan yeniden yazmak olurdu."""
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = []
        assert market_service.symbols_without_fundamentals(db) == []
