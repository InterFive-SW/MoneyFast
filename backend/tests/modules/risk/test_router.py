"""Risk modülü — MCP v2.1 sözleşme testleri.

Bu modülün en önemli davranışı, hesaplayamadığı metriği uydurmaması. Testler
hem yoğunlaşma metriklerinin doğruluğunu hem de geçmiş fiyat gerektiren
metriklerin `None` döndüğünü ve `data_quality`'nin bunu açıkça söylediğini
kontrol eder.
"""

from __future__ import annotations

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

    def test_sector_is_unclassified_rather_than_guessed(self, client):
        """Pozisyon sözleşmesi sektör taşımıyor ve bu modül investment'ın
        fixture'larına uzanmamalı; sözleşmenin kendi talimatı UNCLASSIFIED."""
        body = client.post(URL, json={"positions": EQUAL_HALVES}).json()
        assert body["metrics"]["concentration"]["by_sector"] == {"UNCLASSIFIED": 1.0}

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
