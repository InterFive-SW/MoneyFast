"""Market data collection.

yfinance is stubbed throughout: hitting the real API in a unit suite is slow,
flaky, and rude. What matters here is that one unusable ticker never costs us
the rest of the batch — a single delisted symbol must not blank the dashboard.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ingestor.sources import yfinance_source

PRODUCTS = [
    {"symbol": "TEST-THYAO", "data_symbol": "THYAO.IS"},
    {"symbol": "TEST-AAPL", "data_symbol": "AAPL"},
]


class FakeFastInfo(dict):
    """fast_info behaves like a mapping AND an attribute bag, and which one
    works depends on the yfinance version."""


def install_tickers(monkeypatch, mapping):
    """Stub the yfinance module.

    Mapping values are FACTORIES, not instances: a "delisted ticker" has to
    fail when the source calls yf.Ticker(), not while the test is building
    its fixtures.
    """
    import sys

    module = SimpleNamespace(Ticker=lambda symbol: mapping[symbol]())
    monkeypatch.setitem(sys.modules, "yfinance", module)


def ticker(price=None, previous=None, volume=None, history=None, raises=False):
    def factory():
        if raises:
            raise RuntimeError("delisted")

        info = FakeFastInfo()
        if price is not None:
            info["last_price"] = price
        if previous is not None:
            info["previous_close"] = previous
        if volume is not None:
            info["last_volume"] = volume

        return SimpleNamespace(
            fast_info=info,
            history=lambda period=None, interval=None: history,
        )

    return factory


def frame_for(prices: dict[str, list[float]], volumes: dict[str, list] | None = None):
    """A real DataFrame shaped the way yf.download returns one.

    Columns are a MultiIndex of (field, symbol) — hand-rolling a double for
    this is how you end up passing tests against a shape the provider never
    produces.
    """
    import pandas as pd

    index = pd.date_range("2026-08-19", periods=2, tz="UTC")
    data = {}
    for symbol, series in prices.items():
        data[("Close", symbol)] = series
    for symbol, series in (volumes or {}).items():
        data[("Volume", symbol)] = series
    return pd.DataFrame(data, index=index)


def install_download(monkeypatch, frame):
    import sys
    from types import SimpleNamespace

    module = SimpleNamespace(download=lambda *a, **k: frame, Ticker=lambda s: None)
    monkeypatch.setitem(sys.modules, "yfinance", module)


class TestQuotes:
    """One batched request for the whole universe.

    The per-symbol alternative would be ~95 requests every ten seconds, or
    34,000 an hour — which is how you get rate limited and then blocked.
    """

    def test_price_and_change_are_derived_from_two_bars(self, monkeypatch):
        install_download(monkeypatch, frame_for({"THYAO.IS": [290.0, 300.0]},
                                                {"THYAO.IS": [100, 250]}))
        rows = yfinance_source.fetch_quotes([PRODUCTS[0]])
        assert rows[0]["symbol"] == "TEST-THYAO"
        assert rows[0]["price"] == 300.0
        assert rows[0]["previous_close"] == 290.0
        assert rows[0]["change_amount"] == pytest.approx(10.0)
        assert rows[0]["change_percent"] == pytest.approx(10 / 290 * 100)
        assert rows[0]["volume"] == 250

    def test_the_whole_universe_is_one_request(self, monkeypatch):
        calls = []
        import sys
        from types import SimpleNamespace

        def _download(symbols, **kwargs):
            calls.append(symbols)
            return frame_for({"THYAO.IS": [290.0, 300.0], "AAPL": [210.0, 215.0]})

        monkeypatch.setitem(sys.modules, "yfinance",
                            SimpleNamespace(download=_download, Ticker=lambda s: None))
        rows = yfinance_source.fetch_quotes(PRODUCTS)
        assert len(calls) == 1, "one batch, not one request per symbol"
        assert len(rows) == 2

    def test_timestamp_comes_from_the_provider_bar(self, monkeypatch):
        """Not our clock: the backend derives the disclosed delay from this,
        so now() here would make delayed data look live."""
        install_download(monkeypatch, frame_for({"THYAO.IS": [290.0, 300.0]}))
        rows = yfinance_source.fetch_quotes([PRODUCTS[0]])
        assert rows[0]["market_timestamp"].tzinfo is not None
        assert rows[0]["market_timestamp"].date().isoformat() == "2026-08-20"

    def test_single_bar_leaves_change_null_not_zero(self, monkeypatch):
        """Zero change asserts the price did not move. Unknown is not that."""
        import pandas as pd

        index = pd.date_range("2026-08-20", periods=2, tz="UTC")
        frame = pd.DataFrame({("Close", "THYAO.IS"): [float("nan"), 300.0]}, index=index)
        install_download(monkeypatch, frame)
        rows = yfinance_source.fetch_quotes([PRODUCTS[0]])
        assert rows[0]["change_amount"] is None
        assert rows[0]["change_percent"] is None

    def test_symbol_with_no_data_is_skipped_not_zeroed(self, monkeypatch):
        install_download(monkeypatch, frame_for({"THYAO.IS": [float("nan")] * 2,
                                                 "AAPL": [210.0, 215.0]}))
        rows = yfinance_source.fetch_quotes(PRODUCTS)
        assert [row["symbol"] for row in rows] == ["TEST-AAPL"]

    def test_symbol_absent_from_the_frame_is_skipped(self, monkeypatch):
        """A delisted ticker simply does not come back in the batch."""
        install_download(monkeypatch, frame_for({"AAPL": [210.0, 215.0]}))
        rows = yfinance_source.fetch_quotes(PRODUCTS)
        assert [row["symbol"] for row in rows] == ["TEST-AAPL"]

    def test_empty_frame_yields_nothing(self, monkeypatch):
        import pandas as pd

        install_download(monkeypatch, pd.DataFrame())
        assert yfinance_source.fetch_quotes(PRODUCTS) == []

    def test_products_without_a_data_symbol_are_not_requested(self, monkeypatch):
        install_download(monkeypatch, frame_for({"AAPL": [210.0, 215.0]}))
        assert yfinance_source.fetch_quotes([{"symbol": "X", "data_symbol": None}]) == []


class TestFundamentals:
    """Per-symbol because the provider has no batch form — which is why this
    runs daily rather than every cycle."""

    def _install(self, monkeypatch, info_by_symbol):
        import sys
        from types import SimpleNamespace

        module = SimpleNamespace(
            Ticker=lambda s: SimpleNamespace(info=info_by_symbol.get(s, {})),
            download=lambda *a, **k: None,
        )
        monkeypatch.setitem(sys.modules, "yfinance", module)

    def test_ratios_are_extracted(self, monkeypatch):
        self._install(monkeypatch, {"THYAO.IS": {
            "trailingPE": 8.2, "priceToBook": 1.4, "marketCap": 414086529024,
            "dividendYield": 2.29, "sector": "Industrials",
            "fiftyTwoWeekHigh": 355.5, "fiftyTwoWeekLow": 210.0,
        }})
        rows = yfinance_source.fetch_fundamentals([PRODUCTS[0]])
        assert rows[0]["pe_ratio"] == pytest.approx(8.2)
        assert rows[0]["sector"] == "Industrials"
        assert rows[0]["market_cap"] == 414086529024

    def test_missing_ratio_stays_none(self, monkeypatch):
        """THYAO genuinely has no trailing P/E from this provider. Writing 0
        would make it the cheapest stock on any screen."""
        self._install(monkeypatch, {"THYAO.IS": {"priceToBook": 1.4}})
        rows = yfinance_source.fetch_fundamentals([PRODUCTS[0]])
        assert rows[0]["pe_ratio"] is None
        assert rows[0]["pb_ratio"] == pytest.approx(1.4)

    def test_nan_is_treated_as_missing(self, monkeypatch):
        self._install(monkeypatch, {"THYAO.IS": {"trailingPE": float("nan")}})
        assert yfinance_source.fetch_fundamentals([PRODUCTS[0]])[0]["pe_ratio"] is None

    def test_non_numeric_is_treated_as_missing(self, monkeypatch):
        self._install(monkeypatch, {"THYAO.IS": {"trailingPE": "N/A"}})
        assert yfinance_source.fetch_fundamentals([PRODUCTS[0]])[0]["pe_ratio"] is None

    def test_provider_failure_does_not_lose_the_batch(self, monkeypatch):
        import sys
        from types import SimpleNamespace

        def _ticker(symbol):
            if symbol == "THYAO.IS":
                raise RuntimeError("delisted")
            return SimpleNamespace(info={"trailingPE": 35.6})

        monkeypatch.setitem(sys.modules, "yfinance",
                            SimpleNamespace(Ticker=_ticker, download=lambda *a, **k: None))
        rows = yfinance_source.fetch_fundamentals(PRODUCTS)
        assert [row["symbol"] for row in rows] == ["TEST-AAPL"]

    def test_boolean_is_not_coerced_to_a_number(self, monkeypatch):
        self._install(monkeypatch, {"THYAO.IS": {"trailingPE": True}})
        assert yfinance_source.fetch_fundamentals([PRODUCTS[0]])[0]["pe_ratio"] is None


class FakeFrame:
    def __init__(self, rows):
        self._rows = rows
        self.empty = not rows

    def iterrows(self):
        return iter(self._rows)


class TestCandles:
    def _bar(self):
        return {"Open": 290.0, "High": 305.0, "Low": 289.0, "Close": 300.0, "Volume": 1000}

    def test_bars_are_converted(self, monkeypatch):
        stamp = datetime(2026, 8, 19, tzinfo=timezone.utc)
        frame = FakeFrame([(stamp, self._bar())])
        install_tickers(monkeypatch, {"THYAO.IS": ticker(history=frame)})
        rows = yfinance_source.fetch_candles([PRODUCTS[0]])
        assert rows[0]["symbol"] == "TEST-THYAO"
        assert rows[0]["close"] == 300.0
        assert rows[0]["interval"] == "1d"
        assert rows[0]["timestamp"] == stamp

    def test_naive_timestamps_are_coerced_to_utc(self, monkeypatch):
        naive = datetime(2026, 8, 19)
        frame = FakeFrame([(naive, self._bar())])
        install_tickers(monkeypatch, {"THYAO.IS": ticker(history=frame)})
        rows = yfinance_source.fetch_candles([PRODUCTS[0]])
        assert rows[0]["timestamp"].tzinfo is timezone.utc

    def test_empty_history_is_skipped(self, monkeypatch):
        install_tickers(monkeypatch, {"THYAO.IS": ticker(history=FakeFrame([]))})
        assert yfinance_source.fetch_candles([PRODUCTS[0]]) == []

    def test_none_history_is_skipped(self, monkeypatch):
        install_tickers(monkeypatch, {"THYAO.IS": ticker(history=None)})
        assert yfinance_source.fetch_candles([PRODUCTS[0]]) == []

    def test_unusable_index_row_is_skipped(self, monkeypatch):
        frame = FakeFrame([("not-a-date", self._bar())])
        install_tickers(monkeypatch, {"THYAO.IS": ticker(history=frame)})
        assert yfinance_source.fetch_candles([PRODUCTS[0]]) == []

    def test_provider_failure_does_not_lose_the_batch(self, monkeypatch):
        stamp = datetime(2026, 8, 19, tzinfo=timezone.utc)
        install_tickers(
            monkeypatch,
            {
                "THYAO.IS": ticker(raises=True),
                "AAPL": ticker(history=FakeFrame([(stamp, self._bar())])),
            },
        )
        rows = yfinance_source.fetch_candles(PRODUCTS)
        assert [row["symbol"] for row in rows] == ["TEST-AAPL"]

    def test_product_without_a_data_symbol_is_ignored(self, monkeypatch):
        install_tickers(monkeypatch, {})
        assert yfinance_source.fetch_candles([{"symbol": "X", "data_symbol": ""}]) == []


class TestNumberCoercion:
    def test_nan_is_treated_as_missing(self):
        assert yfinance_source._int_or_none(float("nan")) is None
        assert yfinance_source._first_number(FakeFastInfo(v=float("nan")), "v") is None

    def test_non_numeric_is_treated_as_missing(self):
        assert yfinance_source._int_or_none("lots") is None
        assert yfinance_source._int_or_none(None) is None

    def test_camel_case_fallback(self):
        """fast_info exposes snake_case on some versions and camelCase on
        others; reading only one silently yields no prices after an upgrade."""
        info = FakeFastInfo(lastPrice=12.5)
        assert yfinance_source._first_number(info, "last_price", "lastPrice") == 12.5

    def test_attribute_style_access_also_works(self):
        info = SimpleNamespace(last_price=9.5)
        assert yfinance_source._first_number(info, "last_price") == 9.5

    def test_to_utc_handles_none_and_junk(self):
        assert yfinance_source._to_utc(None) is None
        assert yfinance_source._to_utc(12345) is None


class TestFrameShapeGuards:
    """yfinance returns different frame shapes depending on how many symbols
    were requested and what the provider had. The guards exist because a shape
    surprise must skip one ticker, not blank the whole batch of ninety-four."""

    def _frame(self, closes):
        """A DataFrame stand-in whose "Close" column is whatever we hand it."""
        class Frame:
            empty = False

            def __contains__(self, key):
                return key == "Close"

            def __getitem__(self, key):
                if key == "Close":
                    return closes
                raise KeyError(key)

        return Frame()

    def _run(self, monkeypatch, closes):
        import sys
        import types

        index = SimpleNamespace()
        fake_yf = types.ModuleType("yfinance")
        fake_yf.download = lambda *a, **k: self._frame(closes)
        monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
        return yfinance_source.fetch_quotes([{"symbol": "THYAO", "data_symbol": "THYAO.IS"}])

    def test_a_column_that_reports_membership_but_raises_on_access(self, monkeypatch):
        """A MultiIndex frame can answer `in` truthfully and still raise when
        indexed. Skipping that symbol keeps the other ninety-three."""

        class HostileCloses:
            index = [None]

            def __contains__(self, key):
                return True

            def __getitem__(self, key):
                raise KeyError(key)

        assert self._run(monkeypatch, HostileCloses()) == []

    def test_a_typeerror_is_treated_the_same_way(self, monkeypatch):
        class WrongType:
            index = [None]

            def __contains__(self, key):
                return True

            def __getitem__(self, key):
                raise TypeError("not indexable")

        assert self._run(monkeypatch, WrongType()) == []


class TestFundamentalsSelection:
    def test_a_product_without_a_provider_symbol_is_skipped(self, monkeypatch):
        """Three BIST names are seeded with data_symbol NULL because Yahoo no
        longer quotes them. Requesting them would log an error every day
        forever, for a symbol we already know has no data."""
        import sys

        asked = []

        def _ticker(symbol):
            asked.append(symbol)
            return SimpleNamespace(info={})

        monkeypatch.setitem(
            sys.modules, "yfinance", SimpleNamespace(Ticker=_ticker)
        )
        yfinance_source.fetch_fundamentals([
            {"symbol": "IPEKE"},
            {"symbol": "KOZAL", "data_symbol": None},
            {"symbol": "THYAO", "data_symbol": "THYAO.IS"},
        ])
        assert asked == ["THYAO.IS"], "only the quoted symbol should be requested"
