"""Risk modülü — MCP v2.1 sözleşme testleri.

Bu modülün en önemli davranışı, hesaplayamadığı metriği uydurmaması. Testler
hem yoğunlaşma metriklerinin doğruluğunu hem de geçmiş fiyat gerektiren
metriklerin `None` döndüğünü ve `data_quality`'nin bunu açıkça söylediğini
kontrol eder.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.modules.risk import service

URL = "/api/risk/calculate"

# risk_strategy_tools._normalize() bu anahtarları require() ile arıyor.
REQUIRED_TOP_LEVEL = {"as_of", "source", "is_delayed", "window", "metrics", "assumptions", "data_quality"}


def positions(*specs):
    return [
        {
            "symbol": symbol,
            "quantity": 1,
            "market_value": value,
            "asset_class": asset_class,
            "instrument_currency": currency,
        }
        for symbol, value, asset_class, currency in specs
    ]


EQUAL_HALVES = positions(("TEST-THYAO", 500.0, "EQUITY", "TRY"), ("TEST-SISE", 500.0, "EQUITY", "TRY"))


class TestContract:
    def test_top_level_keys_are_complete(self, client):
        body = client.post(URL, json={"positions": EQUAL_HALVES}).json()
        assert set(body) == REQUIRED_TOP_LEVEL

    def test_data_quality_keys_are_complete(self, client):
        body = client.post(URL, json={"positions": EQUAL_HALVES}).json()
        assert set(body["data_quality"]) == {
            "coverage", "excluded_symbols", "gap_filled_days", "is_statistically_reliable",
        }

    def test_risk_free_rate_is_always_disclosed(self, client):
        """Sharpe, hangi orana göre hesaplandığı bilinmeden yorumlanamaz;
        tool katmanı bu alan yoksa ContractViolationError fırlatıyor."""
        body = client.post(URL, json={"positions": EQUAL_HALVES}).json()
        assert body["assumptions"]["risk_free_rate"] == pytest.approx(service.DEFAULT_RISK_FREE_RATE)
        assert body["assumptions"]["risk_free_rate_source"] == "FIXTURE_POLICY_RATE"

    def test_caller_supplied_rate_is_echoed_and_labelled(self, client):
        body = client.post(URL, json={"positions": EQUAL_HALVES, "risk_free_rate": 0.5}).json()
        assert body["assumptions"]["risk_free_rate"] == pytest.approx(0.5)
        assert body["assumptions"]["risk_free_rate_source"] == "CALLER_SUPPLIED"

    def test_assumptions_echo_every_shaping_parameter(self, client):
        body = client.post(
            URL,
            json={
                "positions": EQUAL_HALVES,
                "lookback": "3M",
                "benchmark_symbol": "XU100",
                "rebalance_assumption": "DAILY_REBALANCE",
                "confidence_level": 0.99,
            },
        ).json()
        assumptions = body["assumptions"]
        assert assumptions["lookback"] == "3M"
        assert assumptions["benchmark_symbol"] == "XU100"
        assert assumptions["rebalance_assumption"] == "DAILY_REBALANCE"
        assert assumptions["confidence_level"] == pytest.approx(0.99)


class TestConcentration:
    def test_two_equal_positions_give_hhi_one_half(self, client):
        body = client.post(URL, json={"positions": EQUAL_HALVES}).json()
        concentration = body["metrics"]["concentration"]
        assert concentration["hhi"] == pytest.approx(0.5)
        assert concentration["effective_n"] == pytest.approx(2.0)

    def test_single_holding_is_maximally_concentrated(self, client):
        body = client.post(
            URL, json={"positions": positions(("TEST-THYAO", 1000.0, "EQUITY", "TRY"))}
        ).json()
        concentration = body["metrics"]["concentration"]
        assert concentration["hhi"] == pytest.approx(1.0)
        assert concentration["effective_n"] == pytest.approx(1.0)
        assert concentration["largest_position"] == {"symbol": "TEST-THYAO", "weight": 1.0}

    def test_top_k_weights_are_cumulative(self, client):
        body = client.post(
            URL,
            json={
                "positions": positions(
                    ("A", 600.0, "EQUITY", "TRY"),
                    ("B", 300.0, "EQUITY", "TRY"),
                    ("C", 100.0, "EQUITY", "TRY"),
                )
            },
        ).json()
        concentration = body["metrics"]["concentration"]
        assert concentration["top_1_weight"] == pytest.approx(0.6)
        assert concentration["top_3_weight"] == pytest.approx(1.0)
        # Yalnızca üç pozisyon var; top_5 hepsini kapsar.
        assert concentration["top_5_weight"] == pytest.approx(1.0)

    def test_breakdowns_use_the_submitted_metadata(self, client):
        body = client.post(
            URL,
            json={
                "positions": positions(
                    ("TEST-THYAO", 700.0, "EQUITY", "TRY"),
                    ("TEST-AAPL", 300.0, "ETF", "USD"),
                )
            },
        ).json()
        concentration = body["metrics"]["concentration"]
        assert concentration["by_asset_class"] == {"EQUITY": 0.7, "ETF": 0.3}
        assert concentration["by_currency"] == {"TRY": 0.7, "USD": 0.3}

    def test_sector_defaults_to_unclassified_when_the_caller_omits_it(self, client):
        """Sektörsüz bir pozisyon tahmin edilmez; bu modül investment'ın
        verisine uzanmaz, gelen neyse onu raporlar."""
        body = client.post(URL, json={"positions": EQUAL_HALVES}).json()
        assert body["metrics"]["concentration"]["by_sector"] == {"UNCLASSIFIED": 1.0}

    def test_sector_reaches_the_breakdown_when_it_is_supplied(self, client):
        """`PositionIn` sektörü taşımıyordu ve `extra: "ignore"` onu sessizce
        atıyordu, dolayısıyla veritabanından gelen sektör kırılıma varmadan
        bir katman önce kayboluyor ve HER portföy {"UNCLASSIFIED": 1.0}
        olarak raporlanıyordu."""
        body = client.post(
            URL,
            json={
                "positions": [
                    {
                        "symbol": "THYAO", "quantity": 1, "market_value": 700.0,
                        "asset_class": "EQUITY", "instrument_currency": "TRY",
                        "sector": "Industrials",
                    },
                    {
                        "symbol": "GARAN", "quantity": 1, "market_value": 300.0,
                        "asset_class": "EQUITY", "instrument_currency": "TRY",
                        "sector": "Financials",
                    },
                ]
            },
        ).json()
        assert body["metrics"]["concentration"]["by_sector"] == {
            "Industrials": 0.7,
            "Financials": 0.3,
        }

    def test_worthless_portfolio_does_not_divide_by_zero(self):
        result = service.concentration(positions(("A", 0.0, "EQUITY", "TRY")))
        assert result["hhi"] == 0.0
        assert result["effective_n"] == 0.0

    def test_empty_position_list_has_no_sector_breakdown(self):
        assert service.concentration([])["by_sector"] == {}


class TestWithoutHistory:
    """The degraded path: nothing has been ingested yet."""

    @pytest.mark.parametrize(
        "metric",
        [
            "volatility_annualized", "downside_deviation_annualized", "max_drawdown",
            "var", "cvar", "sharpe_ratio", "beta", "correlation_to_benchmark",
        ],
    )
    def test_metrics_are_none_not_invented(self, client, metric):
        """An invented volatility figure is worse than an absent one, because
        the absent one is obviously absent."""
        body = client.post(URL, json={"positions": EQUAL_HALVES, "benchmark_symbol": "XU100"}).json()
        assert body["metrics"][metric] is None

    def test_symbols_without_history_are_named(self, client):
        body = client.post(URL, json={"positions": EQUAL_HALVES}).json()
        quality = body["data_quality"]
        assert quality["coverage"] == 0.0
        assert quality["is_statistically_reliable"] is False
        assert set(quality["excluded_symbols"]) == {"TEST-THYAO", "TEST-SISE"}

    def test_observation_count_is_zero(self, client):
        body = client.post(URL, json={"positions": EQUAL_HALVES}).json()
        assert body["window"]["observation_count"] == 0

    def test_benchmark_is_still_echoed_so_the_tool_does_not_null_a_real_beta(self, client):
        """The MCP normalizer forces beta to None when this field is empty.
        Blanking it because history was missing would also discard a beta we
        had successfully computed on a different request."""
        body = client.post(URL, json={"positions": EQUAL_HALVES, "benchmark_symbol": "XU100"}).json()
        assert body["assumptions"]["benchmark_symbol"] == "XU100"
        assert body["assumptions"]["benchmark_history_available"] is False


class TestWithRealHistory:
    """The path that matters: candles exist and the metrics are computed."""

    @staticmethod
    def _book():
        import random
        from datetime import datetime, timedelta, timezone

        random.seed(11)
        out = {}
        for symbol in ("TEST-THYAO", "TEST-SISE", "XU100"):
            price, bars, day = 100.0, [], datetime(2025, 1, 1, tzinfo=timezone.utc)
            for index in range(300):
                price *= 1 + random.gauss(0.0004, 0.018)
                bars.append((day + timedelta(days=index), price))
            out[symbol] = bars
        return out

    def _calculate(self, **kwargs):
        book = self._book()
        return service.calculate(
            EQUAL_HALVES, closes_for=lambda symbol: book.get(symbol, []), **kwargs
        )

    def test_volatility_is_a_real_annualised_number(self):
        result = self._calculate()
        volatility = result["metrics"]["volatility_annualized"]
        assert volatility is not None
        # Daily sigma ~1.8% annualises to roughly 0.29.
        assert 0.05 < volatility < 1.0

    def test_drawdown_is_negative_and_dated(self):
        drawdown = self._calculate()["metrics"]["max_drawdown"]
        assert drawdown["value"] < 0
        assert drawdown["peak_date"] and drawdown["trough_date"]

    def test_var_is_reported_as_a_fraction_and_an_amount(self):
        var = self._calculate()["metrics"]["var"]
        assert var["value_fraction"] < 0
        assert var["value_currency"] < 0
        assert var["method"] == "HISTORICAL"

    def test_cvar_is_never_milder_than_var(self):
        metrics = self._calculate()["metrics"]
        assert metrics["cvar"]["value_fraction"] <= metrics["var"]["value_fraction"]

    def test_beta_and_correlation_against_the_benchmark(self):
        metrics = self._calculate(benchmark_symbol="XU100")["metrics"]
        assert metrics["beta"] is not None
        assert -1.0 <= metrics["correlation_to_benchmark"] <= 1.0

    def test_coverage_and_reliability_reflect_the_real_sample(self):
        quality = self._calculate()["data_quality"]
        assert quality["coverage"] == 1.0
        assert quality["excluded_symbols"] == []
        assert quality["is_statistically_reliable"] is True

    def test_window_reports_real_dates_and_observation_count(self):
        window = self._calculate()["window"]
        assert window["observation_count"] > 200
        assert window["start_date"] < window["end_date"]

    def test_a_short_lookback_reduces_the_sample(self):
        assert (
            self._calculate(lookback="1M")["window"]["observation_count"]
            < self._calculate(lookback="1Y")["window"]["observation_count"]
        )

    def test_a_short_lookback_is_flagged_unreliable(self):
        """22 observations is not enough to state a volatility as firm."""
        assert self._calculate(lookback="1M")["data_quality"]["is_statistically_reliable"] is False

    def test_a_symbol_without_history_is_excluded_not_assumed_flat(self):
        book = self._book()
        book.pop("TEST-SISE")
        result = service.calculate(
            EQUAL_HALVES, closes_for=lambda symbol: book.get(symbol, [])
        )
        assert result["data_quality"]["excluded_symbols"] == ["TEST-SISE"]
        assert result["data_quality"]["coverage"] == pytest.approx(0.5)
        # Half the portfolio is unmeasured, so the figure is not firm.
        assert result["data_quality"]["is_statistically_reliable"] is False

    def test_correlation_matrix_is_returned_when_requested(self):
        matrix = self._calculate(metrics=["CORRELATION_MATRIX"])["metrics"]["correlation_matrix"]
        assert matrix["symbols"] == ["TEST-SISE", "TEST-THYAO"]
        assert matrix["matrix"][0][0] == pytest.approx(1.0)


class TestMetricSelection:
    def test_default_omits_the_correlation_matrix(self, client):
        body = client.post(URL, json={"positions": EQUAL_HALVES}).json()
        assert "correlation_matrix" not in body["metrics"]

    def test_explicit_selection_returns_only_what_was_asked_for(self, client):
        body = client.post(
            URL, json={"positions": EQUAL_HALVES, "metrics": ["CONCENTRATION"]}
        ).json()
        assert set(body["metrics"]) == {"concentration"}

    def test_correlation_matrix_can_be_requested_explicitly(self, client):
        body = client.post(
            URL, json={"positions": EQUAL_HALVES, "metrics": ["CORRELATION_MATRIX"]}
        ).json()
        assert body["metrics"] == {"correlation_matrix": None}

    def test_selection_is_case_insensitive(self, client):
        body = client.post(
            URL, json={"positions": EQUAL_HALVES, "metrics": ["concentration"]}
        ).json()
        assert "concentration" in body["metrics"]


class TestInvalidInput:
    def test_empty_positions_is_a_client_error(self, client):
        """Sıfırlanmış bir HHI "mükemmel çeşitlendirilmiş" gibi okunurdu."""
        response = client.post(URL, json={"positions": []})
        assert response.status_code == 400

    def test_extra_position_keys_are_tolerated(self, client):
        """Ajan get_portfolio_positions çıktısını olduğu gibi geçiriyor."""
        payload = dict(EQUAL_HALVES[0], opened_at="2026-01-15", isin=None, weight=0.5)
        response = client.post(URL, json={"positions": [payload]})
        assert response.status_code == 200


class TestHealth:
    def test_health_reports_the_module(self, client):
        assert client.get("/api/risk/health").json() == {"status": "ok", "module": "risk"}


class TestTimestampRendering:
    def test_a_datetime_renders_as_iso_utc(self):
        from datetime import datetime, timezone

        from app.modules.risk import service as risk_service

        stamp = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
        assert risk_service._iso(stamp) == "2026-08-20T09:00:00Z"

    def test_a_non_datetime_is_stringified_rather_than_raising(self):
        """Some drivers hand back a string; raising here would lose a
        computed result over a formatting detail."""
        from app.modules.risk import service as risk_service

        assert risk_service._iso("2026-08-20") == "2026-08-20"


# ---------------------------------------------------------------------------
# GET /profile — the Risk page.
#
# Distinct from /calculate above, which is frozen against the MCP contract and
# takes positions in the body. This one resolves them from the SESSION: the
# page shows the caller's own risk, and a position list a client could rewrite
# would let anyone render someone else's portfolio.
# ---------------------------------------------------------------------------
PROFILE_URL = "/api/risk/profile"


@pytest.fixture()
def as_user(client):
    """Sign the request in and stub the data the profile reads."""
    from app.core.deps import get_current_user_id
    from app.main import app

    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)


def _stub(mocker, holdings, income=0.0, spending=None, declared=None):
    from app.modules.banking import service as banking_service
    from app.modules.investment import market_service
    from app.modules.risk import store

    mocker.patch.object(market_service, "holdings", return_value=holdings)
    mocker.patch.object(market_service, "candle_closes", return_value=[])
    mocker.patch.object(banking_service, "income_total", return_value=income)
    mocker.patch.object(
        banking_service, "spending_by_category", return_value=spending or []
    )
    # Anket doldurulmamış varsayılan. Mock bir Session bırakılırsa sorgu bir
    # MagicMock döner ve profil şeması onu string sanır.
    mocker.patch.object(store, "latest_profile", return_value=declared)


def _holding(symbol="THYAO", price=300.0, sector="Industrials", quantity=10):
    return {
        "symbol": symbol, "quantity": quantity, "price": price,
        "sector": sector, "currency": "TRY", "avg_cost": price,
    }


def test_profile_requires_a_session(client):
    """Unauthenticated it would have to guess whose risk to report."""
    assert client.get(PROFILE_URL).status_code == 401


def test_profile_reports_the_score_and_its_components(as_user, mocker):
    _stub(mocker, [_holding(), _holding("ASELS", 400.0)])
    body = as_user.get(PROFILE_URL).json()
    assert body["position_count"] == 2
    assert {c["name"] for c in body["components"]} == {
        "volatility", "concentration", "drawdown"
    }


def test_an_unpriced_holding_is_named_rather_than_dropped_silently(as_user, mocker):
    _stub(mocker, [_holding(), _holding("BERA", price=None)])
    body = as_user.get(PROFILE_URL).json()
    assert body["position_count"] == 1
    assert any("BERA" in warning for warning in body["warnings"])


def test_an_empty_portfolio_says_so_instead_of_scoring_zero(as_user, mocker):
    """A score of 0 would read as "maximum risk" for someone holding nothing."""
    _stub(mocker, [])
    body = as_user.get(PROFILE_URL).json()
    assert body["score"] is None
    assert body["position_count"] == 0
    assert body["warnings"]


def test_cashflow_comes_from_the_ledger(as_user, mocker):
    _stub(
        mocker, [_holding()],
        income=54286.0,
        spending=[{"category": "Market", "amount": 12000.0},
                  {"category": "Kira", "amount": 8000.0}],
    )
    cashflow = as_user.get(PROFILE_URL).json()["cashflow"]
    assert cashflow["monthly_income"] == pytest.approx(54286.0)
    assert cashflow["monthly_expense"] == pytest.approx(20000.0)
    assert cashflow["savings_rate"] == pytest.approx((54286.0 - 20000.0) / 54286.0, rel=1e-4)


def test_no_income_leaves_the_savings_rate_unknown(as_user, mocker):
    """0% would claim they spent exactly what they earned."""
    _stub(mocker, [_holding()], income=0.0,
          spending=[{"category": "Market", "amount": 500.0}])
    assert as_user.get(PROFILE_URL).json()["cashflow"]["savings_rate"] is None


def test_the_raw_metrics_are_returned_alongside_the_score(as_user, mocker):
    """Nothing on the page should be unverifiable."""
    _stub(mocker, [_holding()])
    body = as_user.get(PROFILE_URL).json()
    assert "concentration" in body["metrics"]


class TestConcentrationBuckets:
    """The breakdowns were reporting facts about a portfolio nobody owned.

    `by_sector` was hardcoded to `{"UNCLASSIFIED": 1.0}` because the position
    contract did not carry a sector; it does now. `by_currency` reads
    `instrument_currency`, which the profile endpoint was not sending. And the
    weights themselves were taken from unconverted values, so a 481-dollar
    holding was weighed against a 404-lira one as though they were the same
    size.
    """

    def test_sectors_are_bucketed_from_the_positions(self):
        result = service.concentration([
            {"symbol": "AAPL", "market_value": 750.0, "sector": "Technology"},
            {"symbol": "GARAN", "market_value": 250.0, "sector": "Financial Services"},
        ])
        assert result["by_sector"] == {"Technology": 0.75, "Financial Services": 0.25}

    def test_an_instrument_without_a_sector_is_unclassified(self):
        result = service.concentration([
            {"symbol": "AAPL", "market_value": 500.0, "sector": "Technology"},
            {"symbol": "XAUUSD", "market_value": 500.0},
        ])
        assert result["by_sector"] == {"Technology": 0.5, "UNCLASSIFIED": 0.5}

    def test_currencies_are_bucketed(self):
        result = service.concentration([
            {"symbol": "AAPL", "market_value": 800.0, "instrument_currency": "USD"},
            {"symbol": "GARAN", "market_value": 200.0, "instrument_currency": "TRY"},
        ])
        assert result["by_currency"] == {"USD": 0.8, "TRY": 0.2}


def test_profile_weights_are_taken_from_converted_values(as_user, mocker):
    """A dollar holding and a lira holding are not comparable numbers.

    Unconverted, MSFT at 481 USD and ASELS at 404 TRY look like a balanced
    portfolio. Converted, MSFT is 98% of it — and concentration is computed
    from exactly these weights.
    """
    from app.modules.investment import ai_service, market_service
    from app.modules.banking import service as banking_service
    from app.modules.risk import store as risk_store

    mocker.patch.object(market_service, "holdings", return_value=[
        {"symbol": "MSFT", "quantity": 1, "price": 481.0, "currency": "USD",
         "sector": "Technology", "avg_cost": 481.0},
        {"symbol": "ASELS", "quantity": 1, "price": 404.0, "currency": "TRY",
         "sector": "Industrials", "avg_cost": 402.0},
    ])
    mocker.patch.object(market_service, "latest_quotes", return_value={})
    mocker.patch.object(market_service, "candle_closes", return_value=[])
    # TRY: 1.0 is the conversion target and `_convert` requires it, exactly
    # as the real fx_rates() supplies it.
    mocker.patch.object(ai_service, "fx_rates", return_value={"TRY": 1.0, "USD": 48.0})
    mocker.patch.object(banking_service, "income_total", return_value=0.0)
    mocker.patch.object(banking_service, "spending_by_category", return_value=[])
    mocker.patch.object(risk_store, "latest_profile", return_value=None)

    body = as_user.get(PROFILE_URL).json()
    concentration = body["metrics"]["concentration"]

    assert concentration["largest_position"]["symbol"] == "MSFT"
    assert concentration["top_1_weight"] > 0.9
    assert set(concentration["by_sector"]) == {"Technology", "Industrials"}
    assert set(concentration["by_currency"]) == {"USD", "TRY"}


def test_a_holding_with_no_exchange_rate_is_named_not_guessed(as_user, mocker):
    from app.modules.investment import ai_service, market_service
    from app.modules.banking import service as banking_service
    from app.modules.risk import store as risk_store

    mocker.patch.object(market_service, "holdings", return_value=[
        {"symbol": "MSFT", "quantity": 1, "price": 481.0, "currency": "USD",
         "sector": "Technology", "avg_cost": 481.0},
    ])
    mocker.patch.object(market_service, "latest_quotes", return_value={})
    mocker.patch.object(market_service, "candle_closes", return_value=[])
    # No USD rate: the dollar value cannot be stated in lira at all.
    mocker.patch.object(ai_service, "fx_rates", return_value={"TRY": 1.0})
    mocker.patch.object(banking_service, "income_total", return_value=0.0)
    mocker.patch.object(banking_service, "spending_by_category", return_value=[])
    mocker.patch.object(risk_store, "latest_profile", return_value=None)

    body = as_user.get(PROFILE_URL).json()
    assert body["position_count"] == 0
    assert any("MSFT" in w and "kur" in w for w in body["warnings"])


# --------------------------------------------------------------------------
# Faz 1: ölçülen değerin gerçekten taşınması
# --------------------------------------------------------------------------
class TestAssetClassReachesTheBreakdown:
    """`holdings()` ürün tipini baştan beri döndürüyordu; router onun üzerine
    "EQUITY" yazıyordu, dolayısıyla altından başka bir şey tutmayan bir
    portföy bile `{"EQUITY": 1.0}` olarak raporlanıyordu."""

    def test_the_real_product_type_is_used(self, as_user, mocker):
        _stub(
            mocker,
            [
                {**_holding("THYAO", 700.0, quantity=1), "product_type": "EQUITY"},
                {**_holding("ALTIN", 300.0, quantity=1), "product_type": "COMMODITY"},
            ],
        )
        body = as_user.get(PROFILE_URL).json()
        assert body["metrics"]["concentration"]["by_asset_class"] == {
            "EQUITY": 0.7,
            "COMMODITY": 0.3,
        }

    def test_a_missing_product_type_falls_back_rather_than_crashing(self, as_user, mocker):
        _stub(mocker, [_holding("THYAO", 700.0, quantity=1)])
        body = as_user.get(PROFILE_URL).json()
        assert body["metrics"]["concentration"]["by_asset_class"] == {"EQUITY": 1.0}


class TestLookbackIsValidated:
    """`window_for` tanımadığı her değer için 252 bara düşüyor, yani bir yazım
    hatası bir yıllık veriyi kullanıcının yazdığı etiketle geri veriyordu."""

    def test_an_unknown_lookback_is_rejected(self, client):
        response = client.post(URL, json={"positions": EQUAL_HALVES, "lookback": "1Yil"})
        assert response.status_code == 422

    def test_lookback_is_case_insensitive(self, client):
        response = client.post(URL, json={"positions": EQUAL_HALVES, "lookback": "3m"})
        assert response.status_code == 200
        assert response.json()["assumptions"]["lookback"] == "3M"

    def test_an_explicit_null_metrics_is_accepted(self, client):
        """Sözleşme v2.6 varsayılanı olan alanların null gelmesine izin
        veriyor; null "hepsini hesapla" demek, geçersiz bir seçim değil."""
        response = client.post(URL, json={"positions": EQUAL_HALVES, "metrics": None})
        assert response.status_code == 200
        assert "volatility_annualized" in response.json()["metrics"]

    def test_an_unknown_metric_is_rejected(self, client):
        response = client.post(
            URL, json={"positions": EQUAL_HALVES, "metrics": ["VOLATILITY", "GAMMA"]}
        )
        assert response.status_code == 422

    def test_the_profile_endpoint_rejects_one_too(self, as_user, mocker):
        _stub(mocker, [_holding()])
        assert as_user.get(f"{PROFILE_URL}?lookback=1Yil").status_code == 422


class TestWindowHonesty:
    def test_the_requested_bar_count_is_disclosed(self, client):
        """`observation_count` ile birlikte okunduğunda "5 yıl istedim, bir yıl
        aldım" görünür olur; tek başına etiket bunu gizliyordu."""
        body = client.post(URL, json={"positions": EQUAL_HALVES, "lookback": "5Y"}).json()
        assert body["assumptions"]["lookback_bars_requested"] == 1261
        assert body["assumptions"]["lookback"] == "5Y"

    def test_history_limit_covers_the_extra_bar_the_first_return_needs(self):
        assert service.history_limit("1Y") == 253
        assert service.history_limit("1M") == 23

    def test_the_router_asks_for_the_window_the_lookback_needs(self, client, mocker):
        """Mum okuyucusunun kendi 260 satırlık varsayılanı vardı; 1Y'den uzun
        her pencere sessizce kırpılıyordu."""
        from app.modules.investment import market_service

        reader = mocker.patch.object(market_service, "candle_closes", return_value=[])
        client.post(URL, json={"positions": EQUAL_HALVES, "lookback": "5Y"})
        assert reader.call_args.kwargs["limit"] == 1261


class TestDelayedFlag:
    """Her yanıtta `False` sabitlenmişti. Uzun bir hafta sonundan sonra en yeni
    kapanış üç günlük olur ve asistan bu alanı tazelik olarak yazıyor."""

    def test_a_stale_terminal_bar_is_reported_as_delayed(self):
        from datetime import datetime, timedelta, timezone

        old = datetime.now(timezone.utc) - timedelta(days=4)
        assert service._is_delayed(old) is True

    def test_a_bar_from_today_is_not(self):
        from datetime import datetime, timezone

        assert service._is_delayed(datetime.now(timezone.utc)) is False

    def test_an_unreadable_stamp_counts_as_delayed(self):
        """Gösteremediğimiz bir güncelliği iddia etmemek doğru yön."""
        assert service._is_delayed(None) is True
        assert service._is_delayed("2026-08-26") is True


# --------------------------------------------------------------------------
# Faz 2: risk tolerans anketi ve uyum karşılaştırması
# --------------------------------------------------------------------------
COMPLETE_ANSWERS = {
    "horizon": "3_5y",
    "drawdown_reaction": "hold",
    "experience": "stocks",
    "liquidity": "maybe",
    "income_stability": "mostly",
    "goal": "balanced",
}


class TestQuestionnaireEndpoint:
    def test_the_form_is_public(self, client):
        """Sorularda kişisel veri yok. Formu görmek için giriş yapmak
        zorunda kalmak, testi doldurma ihtimalini düşürmekten başka işe
        yaramaz; CEVAP göndermek oturuma bağlı."""
        response = client.get("/api/risk/questionnaire")
        assert response.status_code == 200
        body = response.json()
        assert len(body["questions"]) == 6
        assert body["version"]

    def test_the_form_does_not_leak_the_scoring(self, client):
        """Seçeneklerin puanını göstermek anketi bir teste çevirir ve
        insanlar teste cevap verir, kendilerine değil."""
        body = client.get("/api/risk/questionnaire").json()
        for question in body["questions"]:
            for option in question["options"]:
                assert set(option) == {"value", "label"}


class TestAssessmentEndpoint:
    def test_submitting_requires_a_session(self, client):
        assert client.post(PROFILE_URL.replace("/profile", "/assessment"),
                           json={"answers": COMPLETE_ANSWERS}).status_code == 401

    def test_a_complete_submission_is_stored_and_scored(self, as_user, mocker):
        from app.modules.risk import store
        from types import SimpleNamespace
        from datetime import datetime, timezone

        saved = SimpleNamespace(
            tolerance_level="Orta", investment_horizon="3-5 yıl",
            updated_at=datetime.now(timezone.utc), questionnaire_version="v1",
        )
        record = mocker.patch.object(store, "record_assessment", return_value=saved)
        body = as_user.post("/api/risk/assessment", json={"answers": COMPLETE_ANSWERS}).json()
        assert body["tolerance_level"] == "Orta"
        assert body["raw_score"] > 0
        assert record.call_args.args[2] == COMPLETE_ANSWERS

    def test_a_partial_submission_is_refused(self, as_user):
        """Boşları sıfır sayıp puanlamak, yarıda bırakan birine temkinli bir
        tolerans atfeder — ve o tolerans sonra portföyüyle karşılaştırılır."""
        partial = dict(COMPLETE_ANSWERS)
        del partial["goal"]
        response = as_user.post("/api/risk/assessment", json={"answers": partial})
        assert response.status_code == 422
        assert "goal" in response.json()["detail"]

    def test_an_unknown_option_is_refused(self, as_user):
        response = as_user.post(
            "/api/risk/assessment", json={"answers": {**COMPLETE_ANSWERS, "goal": "moon"}}
        )
        assert response.status_code == 422
        assert "goal=moon" in response.json()["detail"]


class TestProfileCarriesTheDeclaration:
    def _declared(self, level="Orta"):
        from types import SimpleNamespace
        from datetime import datetime, timezone

        return SimpleNamespace(
            tolerance_level=level, investment_horizon="3-5 yıl",
            updated_at=datetime.now(timezone.utc), questionnaire_version="v1",
        )

    def test_without_a_questionnaire_the_page_still_opens(self, as_user, mocker):
        """Yumuşak kapı: ölçüm gösterilir, karşılaştırma bekler. Sayfayı
        kapatmak, kullanıcıyı ölçümünden de mahrum bırakırdı."""
        _stub(mocker, [_holding()], declared=None)
        body = as_user.get(PROFILE_URL).json()
        assert body["declared"] is None
        assert body["suitability"]["alignment"] == "UNKNOWN"
        assert body["position_count"] == 1

    def test_a_declaration_produces_a_comparison(self, as_user, mocker):
        _stub(mocker, [_holding()], declared=self._declared("Yüksek"))
        body = as_user.get(PROFILE_URL).json()
        assert body["declared"]["tolerance_level"] == "Yüksek"
        assert body["suitability"]["declared_tolerance"] == "Yüksek"
        assert body["suitability"]["alignment"] in {
            "ALIGNED", "PORTFOLIO_RISKIER", "PORTFOLIO_CALMER", "UNKNOWN",
        }

    def test_an_unmeasurable_portfolio_cannot_be_compared(self, as_user, mocker):
        """Yarısı bilinen bir karşılaştırma, karşılaştırma değildir."""
        _stub(mocker, [], declared=self._declared())
        body = as_user.get(PROFILE_URL).json()
        assert body["declared"]["tolerance_level"] == "Orta"
        assert body["suitability"]["alignment"] == "UNKNOWN"


# --------------------------------------------------------------------------
# Faz 3: "ne olur?" simülasyonu
# --------------------------------------------------------------------------
SIMULATE_URL = "/api/risk/simulate"


def _stub_product(mocker, symbol="NVDA", price=100.0, currency="TRY",
                  sector="Technology", product_type="stock"):
    """Portföyde OLMAYAN bir sembol için ürün ve fiyat."""
    from types import SimpleNamespace
    from app.modules.investment import market_service

    mocker.patch.object(
        market_service, "get_product",
        return_value=SimpleNamespace(
            product_type=product_type, sector=sector, currency_code=currency
        ),
    )
    mocker.patch.object(
        market_service, "latest_quotes",
        return_value={symbol: {"price": price, "currency": currency}},
    )


class TestSimulateEndpoint:
    def test_it_requires_a_session(self, client):
        assert client.post(
            SIMULATE_URL, json={"changes": [{"symbol": "THYAO", "quantity_delta": 1}]}
        ).status_code == 401

    def test_an_empty_portfolio_has_nothing_to_compare_against(self, as_user, mocker):
        _stub(mocker, [])
        response = as_user.post(
            SIMULATE_URL, json={"changes": [{"symbol": "THYAO", "quantity_delta": 1}]}
        )
        assert response.status_code == 400

    def test_at_least_one_change_is_required(self, as_user, mocker):
        _stub(mocker, [_holding()])
        assert as_user.post(SIMULATE_URL, json={"changes": []}).status_code == 422

    def test_an_invalid_lookback_is_refused(self, as_user, mocker):
        _stub(mocker, [_holding()])
        response = as_user.post(SIMULATE_URL, json={
            "changes": [{"symbol": "THYAO", "quantity_delta": 1}], "lookback": "1Yil",
        })
        assert response.status_code == 422

    def test_an_explicit_lookback_is_normalised_and_used(self, as_user, mocker):
        """Pencere küçük harfle gelebilir; sunucu onu kanonik hâle çevirip
        mum okuyucusuna o pencerenin gerektirdiği bar sayısını sorar."""
        from app.modules.investment import market_service

        _stub(mocker, [_holding("THYAO", 300.0, quantity=10)])
        reader = mocker.patch.object(market_service, "candle_closes", return_value=[])
        response = as_user.post(SIMULATE_URL, json={
            "changes": [{"symbol": "THYAO", "quantity_delta": 1}], "lookback": "3m",
        })
        assert response.status_code == 200
        assert reader.call_args.kwargs["limit"] == service.history_limit("3M")

    def test_buying_more_of_the_only_holding_leaves_concentration_alone(self, as_user, mocker):
        """Tek pozisyonlu bir portföyde daha fazla almak yoğunlaşmayı
        değiştirmez — HHI hâlâ 1,0. Delta sıfır olmalı, None değil."""
        _stub(mocker, [_holding("THYAO", 300.0, quantity=10)])
        body = as_user.post(SIMULATE_URL, json={
            "changes": [{"symbol": "THYAO", "quantity_delta": 10}],
        }).json()
        assert body["current"]["hhi"] == 1.0
        assert body["hypothetical"]["hhi"] == 1.0
        assert body["deltas"]["hhi"] == 0.0

    def test_adding_a_second_name_lowers_concentration(self, as_user, mocker):
        _stub(mocker, [_holding("THYAO", 300.0, quantity=10)])
        _stub_product(mocker, "NVDA", price=300.0)
        body = as_user.post(SIMULATE_URL, json={
            "changes": [{"symbol": "NVDA", "quantity_delta": 10}],
        }).json()
        assert body["hypothetical"]["hhi"] < body["current"]["hhi"]
        assert body["hypothetical"]["position_count"] == 2
        assert body["deltas"]["effective_n"] > 0

    def test_a_zero_delta_leaves_both_sides_identical(self, as_user, mocker):
        """İki tarafın aynı çıktığını doğrulamanın en ucuz yolu."""
        _stub(mocker, [_holding("THYAO", 300.0, quantity=10), _holding("ASELS", 400.0)])
        body = as_user.post(SIMULATE_URL, json={
            "changes": [{"symbol": "THYAO", "quantity_delta": 0}],
        }).json()
        assert body["current"] == body["hypothetical"]
        assert all(value == 0.0 or value is None for value in body["deltas"].values())

    def test_selling_the_whole_portfolio_leaves_nothing_to_measure(self, as_user, mocker):
        _stub(mocker, [_holding("THYAO", 300.0, quantity=10)])
        body = as_user.post(SIMULATE_URL, json={
            "changes": [{"symbol": "THYAO", "quantity_delta": -10}],
        }).json()
        assert body["hypothetical"]["position_count"] == 0
        assert body["hypothetical"]["score"] is None
        # Ölçülemeyen taraf sıfır farkı değil, bilinmeyen farkı üretir.
        assert body["deltas"]["hhi"] is None

    def test_an_unknown_symbol_is_reported_rather_than_silently_dropped(self, as_user, mocker):
        """Sessizce düşen bir değişiklik, kullanıcıya istemediği bir
        karşılaştırmayı doğruymuş gibi okutur."""
        from app.modules.investment import market_service

        _stub(mocker, [_holding("THYAO", 300.0, quantity=10)])
        mocker.patch.object(market_service, "get_product", return_value=None)
        body = as_user.post(SIMULATE_URL, json={
            "changes": [{"symbol": "YOKBOYLE", "quantity_delta": 5}],
        }).json()
        change = body["changes"][0]
        assert change["applied"] is False
        assert "bulunamadı" in change["note"]

    def test_a_symbol_with_no_quote_is_reported(self, as_user, mocker):
        from types import SimpleNamespace
        from app.modules.investment import market_service

        _stub(mocker, [_holding("THYAO", 300.0, quantity=10)])
        mocker.patch.object(
            market_service, "get_product",
            return_value=SimpleNamespace(product_type="stock", sector="Tech", currency_code="TRY"),
        )
        mocker.patch.object(market_service, "latest_quotes", return_value={})
        body = as_user.post(SIMULATE_URL, json={
            "changes": [{"symbol": "NVDA", "quantity_delta": 5}],
        }).json()
        assert body["changes"][0]["applied"] is False
        assert "fiyat" in body["changes"][0]["note"]

    def test_a_symbol_with_no_exchange_rate_is_reported(self, as_user, mocker):
        from types import SimpleNamespace
        from app.modules.investment import ai_service, market_service

        _stub(mocker, [_holding("THYAO", 300.0, quantity=10)])
        mocker.patch.object(
            market_service, "get_product",
            return_value=SimpleNamespace(product_type="stock", sector="Tech", currency_code="GBP"),
        )
        mocker.patch.object(
            market_service, "latest_quotes",
            return_value={"LLOY": {"price": 50.0, "currency": "GBP"}},
        )
        # Yalnızca YENİ sembol için kur bilinmiyor. `holding_value`'yu topluca
        # None'a bağlamak mevcut portföyü de boşaltır ve uç nokta 400 döner --
        # test o zaman kur dalını değil, boş portföy dalını ölçer.
        real_value = ai_service.holding_value
        mocker.patch.object(
            ai_service, "holding_value",
            side_effect=lambda row, rates, *a, **k: (
                None if (row.get("currency") == "GBP") else real_value(row, rates, *a, **k)
            ),
        )
        body = as_user.post(SIMULATE_URL, json={
            "changes": [{"symbol": "LLOY", "quantity_delta": 5}],
        }).json()
        assert body["changes"][0]["applied"] is False
        assert "kur" in body["changes"][0]["note"]

    def test_the_symbol_is_normalised_to_upper_case(self, as_user, mocker):
        _stub(mocker, [_holding("THYAO", 300.0, quantity=10)])
        body = as_user.post(SIMULATE_URL, json={
            "changes": [{"symbol": "thyao", "quantity_delta": 5}],
        }).json()
        assert body["changes"][0]["symbol"] == "THYAO"
        assert body["changes"][0]["applied"] is True

    def test_the_response_never_says_better_or_worse(self, as_user, mocker):
        """Bu bir hesap makinesi, bir öneri motoru değil: iki ölçüm yan yana
        konur, yorumu okuyan yapar."""
        _stub(mocker, [_holding("THYAO", 300.0, quantity=10)])
        text = as_user.post(SIMULATE_URL, json={
            "changes": [{"symbol": "THYAO", "quantity_delta": 5}],
        }).text.lower()
        for banned in ("daha iyi", "daha kötü", "öneri", "tavsiye", "azaltın", "artırın"):
            assert banned not in text, banned


# --------------------------------------------------------------------------
# Faz 4: risk geçmişi
# --------------------------------------------------------------------------
HISTORY_URL = "/api/risk/history"


class TestHistoryEndpoint:
    def test_it_requires_a_session(self, client):
        assert client.get(HISTORY_URL).status_code == 401

    def test_it_returns_the_recorded_points_oldest_first(self, as_user, mocker):
        from datetime import date
        from types import SimpleNamespace
        from app.modules.risk import store

        mocker.patch.object(store, "snapshot_history", return_value=[
            SimpleNamespace(captured_on=date(2026, 8, 25), score=80.0, level="Düşük",
                            volatility=0.19, hhi=0.17, max_drawdown=-0.12, position_count=14),
            SimpleNamespace(captured_on=date(2026, 8, 26), score=83.4, level="Düşük",
                            volatility=0.18, hhi=0.16, max_drawdown=-0.11, position_count=14),
        ])
        body = as_user.get(HISTORY_URL).json()
        assert [point["captured_on"] for point in body["points"]] == [
            "2026-08-25", "2026-08-26",
        ]
        assert body["points"][1]["score"] == 83.4

    def test_it_states_which_window_the_series_was_measured_over(self, as_user, mocker):
        """Noktalar farklı pencerelerden gelseydi seri anlamsız olurdu; hangi
        pencere olduğu söylenmeli."""
        from app.modules.risk import store

        mocker.patch.object(store, "snapshot_history", return_value=[])
        body = as_user.get(HISTORY_URL).json()
        assert body["lookback"] == store.SNAPSHOT_LOOKBACK

    def test_the_window_is_passed_through(self, as_user, mocker):
        from app.modules.risk import store

        history = mocker.patch.object(store, "snapshot_history", return_value=[])
        body = as_user.get(f"{HISTORY_URL}?days=30").json()
        assert history.call_args.args[2] == 30
        assert body["days"] == 30

    def test_an_out_of_range_window_is_refused(self, as_user):
        assert as_user.get(f"{HISTORY_URL}?days=3").status_code == 422
        assert as_user.get(f"{HISTORY_URL}?days=400").status_code == 422

    def test_no_history_yet_is_an_empty_series_not_an_error(self, as_user, mocker):
        from app.modules.risk import store

        mocker.patch.object(store, "snapshot_history", return_value=[])
        body = as_user.get(HISTORY_URL).json()
        assert body["points"] == []


class TestProfileRecordsASnapshot:
    def test_reading_the_page_stores_todays_measurement(self, as_user, mocker):
        """Ayrı bir zamanlanmış iş aynı sayıları başka bir saatte yeniden
        hesaplar ve iki değer ayrışırdı."""
        from app.modules.risk import store

        record = mocker.patch.object(store, "record_snapshot", return_value=None)
        _stub(mocker, [_holding()])
        as_user.get(PROFILE_URL)
        assert record.called
        assert record.call_args.args[2] == "1Y"

    def test_a_non_default_window_is_passed_through_for_the_store_to_refuse(
        self, as_user, mocker
    ):
        from app.modules.risk import store

        record = mocker.patch.object(store, "record_snapshot", return_value=None)
        _stub(mocker, [_holding()])
        as_user.get(f"{PROFILE_URL}?lookback=3M")
        assert record.call_args.args[2] == "3M"


# ---------------------------------------------------------------------------
# GET /api/risk/profile/{user_id} -- the AI-facing summary.
#
# Named subject in the path rather than resolved from a session, because the
# MCP tool server calls it on behalf of a user. That is exactly why it is
# guarded: the backend is also the public ingress, so "internal only" is not
# true of it, and an unguarded endpoint of this shape lets anyone read anyone
# else's risk profile by guessing an id.
# ---------------------------------------------------------------------------
SUMMARY_URL = "/api/risk/profile/user-1"
TOKEN = "TEST-service-key"


@pytest.fixture()
def service_auth(monkeypatch):
    monkeypatch.setenv("BACKEND_API_KEY", TOKEN)
    return {"Authorization": f"Bearer {TOKEN}"}


class TestServiceGuard:
    def test_an_unsigned_request_is_refused(self, client, service_auth, mocker):
        _stub(mocker, [_holding()])
        assert client.get(SUMMARY_URL).status_code == 401

    def test_a_wrong_token_is_refused(self, client, service_auth, mocker):
        _stub(mocker, [_holding()])
        response = client.get(SUMMARY_URL, headers={"Authorization": "Bearer nope"})
        assert response.status_code == 401

    def test_a_user_session_token_does_not_open_it(self, as_user, mocker, service_auth):
        """The session override signs `/profile` in; it must not sign this in.

        The two endpoints answer different questions -- "my risk" and "this
        user's risk" -- and only the second one needs to be trusted about
        whose data it is naming.
        """
        _stub(mocker, [_holding()])
        assert as_user.get(SUMMARY_URL).status_code == 401

    def test_an_unconfigured_key_refuses_rather_than_opens(self, client, monkeypatch, mocker):
        """Missing env var must not silently make this public.

        503 rather than 401: nothing is wrong with the caller's credentials,
        the deployment never configured any.
        """
        monkeypatch.delenv("BACKEND_API_KEY", raising=False)
        _stub(mocker, [_holding()])
        response = client.get(SUMMARY_URL, headers={"Authorization": "Bearer anything"})
        assert response.status_code == 503


class TestSummaryContract:
    def test_top_level_keys_are_complete(self, client, service_auth, mocker):
        """The tool layer raises on a missing key rather than defaulting it."""
        _stub(mocker, [_holding()])
        body = client.get(SUMMARY_URL, headers=service_auth).json()
        assert set(body) == {
            "as_of", "score", "level", "position_count", "suitability",
            "declared", "metrics", "findings", "data_quality", "warnings",
        }

    def test_the_metric_subset_is_exactly_what_the_score_is_built_from(
        self, client, service_auth, mocker
    ):
        _stub(mocker, [_holding()])
        body = client.get(SUMMARY_URL, headers=service_auth).json()
        assert set(body["metrics"]) == {
            "volatility_annualized", "max_drawdown", "hhi", "effective_n",
            "top_3_weight", "largest_position",
        }

    def test_cashflow_never_reaches_the_model(self, client, service_auth, mocker):
        """Income and spending answer no risk question.

        The page carries them because the page shows them to the person they
        belong to. This payload goes into a prompt.
        """
        _stub(mocker, [_holding()], income=54286.0,
              spending=[{"category": "Kira", "amount": 8000.0}])
        body = client.get(SUMMARY_URL, headers=service_auth).json()
        assert "cashflow" not in body
        assert "54286" not in str(body)

    def test_an_unmeasurable_portfolio_scores_null_not_zero(
        self, client, service_auth, mocker
    ):
        """Zero is the worst possible score on a scale where high means calm."""
        _stub(mocker, [])
        body = client.get(SUMMARY_URL, headers=service_auth).json()
        assert body["score"] is None
        assert body["level"] is None
        assert body["position_count"] == 0

    def test_an_unknown_lookback_is_refused(self, client, service_auth, mocker):
        _stub(mocker, [_holding()])
        response = client.get(
            SUMMARY_URL, headers=service_auth, params={"lookback": "1Yil"}
        )
        assert response.status_code == 422


class TestSummaryAgreesWithThePage:
    """The reason this endpoint exists.

    Before it, the chat agent could reach `POST /calculate` and nothing else,
    so "portföyüm ne kadar riskli" got an annualised volatility percentage
    while the risk page showed a 0-100 score and a band. One system, one
    question, two answers. Both surfaces now read one computation, and these
    tests are what stops them drifting apart again.
    """

    def test_score_and_level_match_the_page(self, as_user, service_auth, mocker):
        _stub(mocker, [_holding(), _holding("ASELS", 400.0)])
        page = as_user.get(PROFILE_URL).json()
        summary = as_user.get(SUMMARY_URL, headers=service_auth).json()
        assert summary["score"] == page["score"]
        assert summary["level"] == page["level"]
        assert summary["position_count"] == page["position_count"]

    def test_the_comparison_sentence_matches_the_page(self, as_user, service_auth, mocker):
        declared = mocker.MagicMock(
            tolerance_level="Yüksek", investment_horizon="LONG",
            questionnaire_version="v1",
        )
        declared.updated_at = datetime(2026, 8, 27, tzinfo=timezone.utc)
        _stub(mocker, [_holding()], declared=declared)

        page = as_user.get(PROFILE_URL).json()
        summary = as_user.get(SUMMARY_URL, headers=service_auth).json()
        assert summary["suitability"] == page["suitability"]
        assert summary["declared"]["tolerance_level"] == "Yüksek"

    def test_without_a_questionnaire_the_comparison_is_unknown(
        self, client, service_auth, mocker
    ):
        """UNKNOWN means a side is missing, not that the two disagree."""
        _stub(mocker, [_holding()])
        body = client.get(SUMMARY_URL, headers=service_auth).json()
        assert body["declared"] is None
        assert body["suitability"]["alignment"] == "UNKNOWN"

    def test_excluded_positions_are_named_for_the_model_too(
        self, client, service_auth, mocker
    ):
        """A total that quietly drops a holding is worse than a named gap."""
        _stub(mocker, [_holding(), _holding("BERA", price=None)])
        body = client.get(SUMMARY_URL, headers=service_auth).json()
        assert any("BERA" in warning for warning in body["warnings"])


# ---------------------------------------------------------------------------
# Two boundary bugs found by running the real chat path, not by a test.
#
# Both had the same shape: the body model was tolerant and the surface beside
# it was not, so a payload the system produces itself was refused. The user
# saw "Verilere şu anda ulaşamadım" for data that was present and valid.
# ---------------------------------------------------------------------------
class TestLookbackCasing:
    def test_a_lowercase_window_is_accepted_on_the_page(self, as_user, mocker):
        """The planner writes "1y". `RiskRequest` has always uppercased it;
        the query string refused it with a 422."""
        _stub(mocker, [_holding()])
        response = as_user.get(PROFILE_URL, params={"lookback": "1y"})
        assert response.status_code == 200

    def test_a_lowercase_window_is_accepted_by_the_service_endpoint(
        self, client, service_auth, mocker
    ):
        _stub(mocker, [_holding()])
        response = client.get(SUMMARY_URL, headers=service_auth,
                              params={"lookback": "3m"})
        assert response.status_code == 200

    def test_an_unknown_window_is_still_refused(self, as_user, mocker):
        """Casing is normalised; an unrecognised window is not. `window_for`
        falls back to 252 bars for anything it does not know, so "3Yil" would
        return one year of data under a three-year label."""
        _stub(mocker, [_holding()])
        response = as_user.get(PROFILE_URL, params={"lookback": "3Yil"})
        assert response.status_code == 422
        assert "3Yil" in response.json()["detail"]


class TestNullPositionFields:
    """`get_portfolio_positions` sends `"sector": null` for an unclassified
    instrument. A plain `str = "UNCLASSIFIED"` default only fills in an ABSENT
    key, so every chat risk question died on a 422 the user read as an outage.
    """

    def test_an_explicit_null_sector_becomes_unclassified(self, client):
        body = client.post(URL, json={"positions": [
            {"symbol": "TEST-THYAO", "quantity": 1, "market_value": 1000.0,
             "asset_class": "EQUITY", "sector": None},
        ]}).json()
        assert body["metrics"]["concentration"]["by_sector"] == {"UNCLASSIFIED": 1.0}

    def test_a_null_asset_class_and_currency_fall_back_too(self, client):
        body = client.post(URL, json={"positions": [
            {"symbol": "TEST-THYAO", "quantity": 1, "market_value": 1000.0,
             "asset_class": None, "instrument_currency": None},
        ]}).json()
        concentration = body["metrics"]["concentration"]
        assert concentration["by_asset_class"] == {"EQUITY": 1.0}
        assert concentration["by_currency"] == {"TRY": 1.0}

    def test_a_real_sector_still_survives(self, client):
        """The null fix must not flatten everything to the default."""
        body = client.post(URL, json={"positions": [
            {"symbol": "TEST-THYAO", "quantity": 1, "market_value": 1000.0,
             "sector": "Technology"},
        ]}).json()
        assert body["metrics"]["concentration"]["by_sector"] == {"Technology": 1.0}



class TestMeasurementDisclosure:
    """The page showed a Sharpe ratio and a beta with nothing to read them by.

    `POST /calculate` has produced `window` and `assumptions` all along; the
    profile endpoint dropped both, so the screen could not say what span the
    numbers covered, which index the beta was against, or which rate the
    Sharpe was net of. The MCP contract requires that last one to be disclosed
    wherever Sharpe is presented -- the chat path did it, the page did not.
    """

    def test_the_window_reaches_the_page(self, as_user, mocker):
        _stub(mocker, [_holding()])
        body = as_user.get(PROFILE_URL).json()
        assert set(body["window"]) == {
            "start_date", "end_date", "observation_count", "frequency",
        }

    def test_the_rate_behind_sharpe_is_disclosed(self, as_user, mocker):
        _stub(mocker, [_holding()])
        assumptions = as_user.get(PROFILE_URL).json()["assumptions"]
        assert assumptions["risk_free_rate"] == pytest.approx(
            service.DEFAULT_RISK_FREE_RATE
        )
        assert assumptions["risk_free_rate_source"] == "FIXTURE_POLICY_RATE"

    def test_the_benchmark_is_named(self, as_user, mocker):
        """Beta was computed against XU100 by default and the user was never
        told which index they were being compared to."""
        _stub(mocker, [_holding()])
        assumptions = as_user.get(PROFILE_URL).json()["assumptions"]
        assert assumptions["benchmark_symbol"] == service.DEFAULT_BENCHMARK
        assert "benchmark_history_available" in assumptions

    def test_an_empty_portfolio_discloses_nothing_rather_than_zeroes(
        self, as_user, mocker
    ):
        """Nothing was measured, so there is no span and no rate to state.
        Empty blocks say that; a zeroed observation count would describe a
        measurement that never happened."""
        _stub(mocker, [])
        body = as_user.get(PROFILE_URL).json()
        assert body["window"] == {}
        assert body["assumptions"] == {}

    def test_the_agent_summary_does_not_carry_them(self, client, service_auth, mocker):
        """The agent reaches the same figures through
        `calculate_portfolio_risk_metrics`, whose contract already carries
        both blocks. Duplicating them here would give one turn two places to
        quote the same window from."""
        _stub(mocker, [_holding()])
        body = client.get(SUMMARY_URL, headers=service_auth).json()
        assert "window" not in body
        assert "assumptions" not in body
