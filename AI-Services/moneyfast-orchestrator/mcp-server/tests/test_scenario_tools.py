"""`run_portfolio_scenario`, `get_portfolio_stress_test`, `simulate_position_change`.

Sözleşme v2.13. Üçü de "ne olurdu" sorusunu cevaplıyor ve üçünün cevabı da bir
tahmin değil: ikisi geçmiş getirilerin aritmetiği, biri gerçekten olan günler.

En önemli iddialar:

* `r_squared` betanın ZORUNLU eşlikçisi. Tek başına bir beta, ilişkinin ne
  kadar gerçek olduğu hakkında hiçbir şey söylemiyor -- ölçüldü, gerçek bir
  portföyde dolara karşı beta -0,68 ve r² 0,001;
* `statement` olduğu gibi taşınıyor, çekincesiyle. İkiye bölüp ilk yarıyı
  göstermek, koşulu düşürüp iddiayı bırakmak olur ve uygunluk kapısı zaten
  keser;
* ölçülemeyen sıfırlanmıyor. `None` "ölçemedik", `0.0` "etki yok" -- karşıt
  iddialar.
"""

from __future__ import annotations

import pytest

import scenario_tools
from backend_client import ContractViolationError, UpstreamUnavailableError

SCENARIO_KEYS = {
    "factor", "factor_name", "shock_pct", "lookback", "sensitivity",
    "estimated_impact_pct", "estimated_impact_value", "statement",
    "assumptions", "warnings",
}
SENSITIVITY_KEYS = {
    "beta", "correlation", "r_squared", "observation_count",
    "is_statistically_reliable",
}
STRESS_KEYS = {
    "lookback", "observation_count", "worst_days", "replays", "factor_names",
    "excluded_symbols", "warnings",
}
SIMULATE_KEYS = {"current", "hypothetical", "deltas", "applied", "warnings"}

STATEMENT = (
    "Dolar/TL %10,0 yükselseydi, son 1 yıl ölçülen duyarlılığa göre "
    "portföyünüzün değeri yaklaşık %6,8 azalırdı — ancak geçmiş fiyat "
    "hareketi geleceği belirlemez."
)


def scenario_body(**overrides):
    payload = {
        "factor": "USDTRY", "factor_name": "Dolar/TL", "shock_pct": 10.0,
        "lookback": "1Y", "base_currency": "TRY",
        "sensitivity": {
            "beta": -0.6792, "correlation": -0.0331, "r_squared": 0.0011,
            "observation_count": 222, "is_statistically_reliable": True,
        },
        "estimated_impact_pct": -6.792,
        "estimated_impact_value": -12345.67,
        "statement": STATEMENT,
        "assumptions": ["Etki doğrusal varsayıldı."],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def stress_body(**overrides):
    payload = {
        "lookback": "1Y", "observation_count": 252,
        "worst_days": [{"date": "2026-03-01T00:00:00", "return_pct": -7.52}],
        "replays": {
            "XU100": {
                "start_date": "2026-04-06T00:00:00", "end_date": "2026-04-13T00:00:00",
                "factor_move_pct": 9.91, "portfolio_move_pct": 7.99, "trading_days": 5,
            }
        },
        "factor_names": {"XU100": "BIST 100"},
        "excluded_symbols": [], "warnings": [],
    }
    payload.update(overrides)
    return payload


def simulate_body(**overrides):
    payload = {
        "as_of": "2026-09-01T12:00:00Z",
        "current": {"score": 35.5, "level": "Yüksek", "volatility": 0.34,
                    "hhi": 0.62, "effective_n": 1.6, "max_drawdown": -0.29,
                    "position_count": 3},
        "hypothetical": {"score": 26.8, "level": "Yüksek", "volatility": 0.38,
                         "hhi": 0.71, "effective_n": 1.4, "max_drawdown": -0.31,
                         "position_count": 3},
        "deltas": {"score": -8.7, "volatility": 0.04, "max_drawdown": None},
        "changes": [{"symbol": "AKBNK", "quantity_delta": 500.0,
                     "applied": True, "note": None}],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


class TestScenarioContract:
    @pytest.mark.asyncio
    async def test_keys_match_v213_exactly(self, fake_backend):
        fake_backend.json("scenario", scenario_body())
        out = await scenario_tools.run_portfolio_scenario("u_1", "USDTRY", 10)
        assert set(out) == SCENARIO_KEYS
        assert set(out["sensitivity"]) == SENSITIVITY_KEYS

    @pytest.mark.asyncio
    async def test_the_user_travels_in_the_path(self, fake_backend):
        fake_backend.json("scenario", scenario_body())
        await scenario_tools.run_portfolio_scenario("u_42", "USDTRY", 10)
        assert "/risk/scenario/u_42" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_the_factor_and_shock_are_sent(self, fake_backend):
        fake_backend.json("scenario", scenario_body())
        await scenario_tools.run_portfolio_scenario("u_1", "XU100", -15)
        assert fake_backend.body() == {"factor": "XU100", "shock_pct": -15}

    @pytest.mark.asyncio
    async def test_no_lookback_is_sent_unless_the_caller_named_one(self, fake_backend):
        """Backend'in penceresi risk sayfasının da penceresi."""
        fake_backend.json("scenario", scenario_body())
        await scenario_tools.run_portfolio_scenario("u_1", "XU100", 10)
        assert "lookback" not in fake_backend.body()

    @pytest.mark.asyncio
    async def test_a_named_lookback_is_forwarded(self, fake_backend):
        fake_backend.json("scenario", scenario_body())
        await scenario_tools.run_portfolio_scenario("u_1", "XU100", 10, lookback="3M")
        assert fake_backend.body()["lookback"] == "3M"

    @pytest.mark.asyncio
    async def test_a_weak_relationship_survives_as_a_number(self, fake_backend):
        """Ölçüldü: beta -0,68, r² 0,001. Beta tek başına taşınsaydı, veri
        onu desteklemezken kesinlik kurulurdu."""
        fake_backend.json("scenario", scenario_body())
        out = await scenario_tools.run_portfolio_scenario("u_1", "USDTRY", 10)
        assert out["sensitivity"]["beta"] == pytest.approx(-0.6792)
        assert out["sensitivity"]["r_squared"] == pytest.approx(0.0011)

    @pytest.mark.asyncio
    async def test_the_statement_is_carried_whole(self, fake_backend):
        fake_backend.json("scenario", scenario_body())
        out = await scenario_tools.run_portfolio_scenario("u_1", "USDTRY", 10)
        assert out["statement"] == STATEMENT
        assert "belirlemez" in out["statement"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "missing", ["factor", "factor_name", "sensitivity", "estimated_impact_pct",
                    "statement"]
    )
    async def test_a_missing_key_is_a_contract_violation(self, fake_backend, missing):
        payload = scenario_body()
        del payload[missing]
        fake_backend.json("scenario", payload)
        with pytest.raises(ContractViolationError):
            await scenario_tools.run_portfolio_scenario("u_1", "USDTRY", 10)

    @pytest.mark.asyncio
    async def test_a_non_object_sensitivity_is_refused(self, fake_backend):
        fake_backend.json("scenario", scenario_body(sensitivity=[-0.68]))
        with pytest.raises(ContractViolationError):
            await scenario_tools.run_portfolio_scenario("u_1", "USDTRY", 10)

    @pytest.mark.asyncio
    async def test_a_sensitivity_without_a_beta_is_refused(self, fake_backend):
        """Sıfıra düşürmek "bu faktör portföyü hiç etkilemiyor" demek olurdu."""
        fake_backend.json("scenario", scenario_body(sensitivity={"observation_count": 5}))
        with pytest.raises(ContractViolationError):
            await scenario_tools.run_portfolio_scenario("u_1", "USDTRY", 10)

    @pytest.mark.asyncio
    async def test_an_unmeasured_correlation_stays_null(self, fake_backend):
        sensitivity = scenario_body()["sensitivity"]
        sensitivity["correlation"] = None
        sensitivity["r_squared"] = None
        fake_backend.json("scenario", scenario_body(sensitivity=sensitivity))
        out = await scenario_tools.run_portfolio_scenario("u_1", "USDTRY", 10)
        assert out["sensitivity"]["correlation"] is None
        assert out["sensitivity"]["r_squared"] is None

    @pytest.mark.asyncio
    async def test_an_unknown_impact_value_stays_null(self, fake_backend):
        fake_backend.json("scenario", scenario_body(estimated_impact_value=None))
        out = await scenario_tools.run_portfolio_scenario("u_1", "USDTRY", 10)
        assert out["estimated_impact_value"] is None

    @pytest.mark.asyncio
    async def test_an_unreachable_backend_raises(self, fake_backend, no_sleep):
        fake_backend.fail("scenario")
        with pytest.raises(UpstreamUnavailableError):
            await scenario_tools.run_portfolio_scenario("u_1", "USDTRY", 10)

    def test_the_factor_list_matches_the_documented_set(self):
        """Üç yerde aynı liste: burada, `orchestrator.SCENARIO_FACTORS`'ta ve
        backend'in `scenario.FACTORS`'ında."""
        assert scenario_tools.FACTORS == ("USDTRY", "EURTRY", "XU100", "XAUUSD")


class TestStressContract:
    @pytest.mark.asyncio
    async def test_keys_match_v213_exactly(self, fake_backend):
        fake_backend.json("stress", stress_body())
        out = await scenario_tools.get_portfolio_stress_test("u_1")
        assert set(out) == STRESS_KEYS

    @pytest.mark.asyncio
    async def test_the_user_travels_in_the_path(self, fake_backend):
        fake_backend.json("stress", stress_body())
        await scenario_tools.get_portfolio_stress_test("u_42")
        assert "/risk/stress/u_42" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_a_replay_keeps_both_moves_and_its_dates(self, fake_backend):
        """İkisi EŞ ZAMANLI, nedensel değil; tarihler olmadan bunu söylemek
        de mümkün olmaz."""
        fake_backend.json("stress", stress_body())
        replay = (await scenario_tools.get_portfolio_stress_test("u_1"))["replays"]["XU100"]
        assert replay["factor_move_pct"] == pytest.approx(9.91)
        assert replay["portfolio_move_pct"] == pytest.approx(7.99)
        assert replay["start_date"].startswith("2026-04-06")

    @pytest.mark.asyncio
    async def test_a_named_lookback_is_forwarded(self, fake_backend):
        fake_backend.json("stress", stress_body())
        await scenario_tools.get_portfolio_stress_test("u_1", lookback="6M")
        assert "lookback=6M" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_no_lookback_is_sent_unless_named(self, fake_backend):
        fake_backend.json("stress", stress_body())
        await scenario_tools.get_portfolio_stress_test("u_1")
        assert "lookback=" not in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_a_missing_replays_block_is_a_contract_violation(self, fake_backend):
        payload = stress_body()
        del payload["replays"]
        fake_backend.json("stress", payload)
        with pytest.raises(ContractViolationError):
            await scenario_tools.get_portfolio_stress_test("u_1")

    @pytest.mark.asyncio
    async def test_a_non_object_replay_is_refused(self, fake_backend):
        fake_backend.json("stress", stress_body(replays={"XU100": [1, 2]}))
        with pytest.raises(ContractViolationError):
            await scenario_tools.get_portfolio_stress_test("u_1")

    @pytest.mark.asyncio
    async def test_a_replay_without_dates_is_refused(self, fake_backend):
        fake_backend.json("stress", stress_body(replays={"XU100": {"factor_move_pct": 1}}))
        with pytest.raises(ContractViolationError):
            await scenario_tools.get_portfolio_stress_test("u_1")

    @pytest.mark.asyncio
    async def test_no_measurable_episode_is_an_empty_body(self, fake_backend):
        """Ölçülemeyen faktör listede YER ALMAZ, sıfırla görünmez -- sıfır
        "o faktör portföyü hiç etkilemedi" demek olurdu."""
        fake_backend.json("stress", stress_body(replays={}, worst_days=[]))
        out = await scenario_tools.get_portfolio_stress_test("u_1")
        assert out["replays"] == {}
        assert out["worst_days"] == []

    @pytest.mark.asyncio
    async def test_an_unreachable_backend_raises(self, fake_backend, no_sleep):
        fake_backend.fail("stress")
        with pytest.raises(UpstreamUnavailableError):
            await scenario_tools.get_portfolio_stress_test("u_1")


class TestSimulateContract:
    @pytest.mark.asyncio
    async def test_keys_match_v213_exactly(self, fake_backend):
        fake_backend.json("simulate", simulate_body())
        out = await scenario_tools.simulate_position_change(
            "u_1", [{"symbol": "AKBNK", "quantity_delta": 500}]
        )
        assert set(out) == SIMULATE_KEYS

    @pytest.mark.asyncio
    async def test_the_user_travels_in_the_path(self, fake_backend):
        fake_backend.json("simulate", simulate_body())
        await scenario_tools.simulate_position_change(
            "u_42", [{"symbol": "AKBNK", "quantity_delta": 1}]
        )
        assert "/risk/simulate/u_42" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_both_sides_travel_so_the_reader_compares(self, fake_backend):
        fake_backend.json("simulate", simulate_body())
        out = await scenario_tools.simulate_position_change(
            "u_1", [{"symbol": "AKBNK", "quantity_delta": 500}]
        )
        assert out["current"]["score"] == 35.5
        assert out["hypothetical"]["score"] == 26.8

    @pytest.mark.asyncio
    async def test_an_unmeasurable_delta_stays_null(self, fake_backend):
        """Sıfır "değişmedi" diye okunur; bu "söyleyemiyoruz"dan farklı."""
        fake_backend.json("simulate", simulate_body())
        out = await scenario_tools.simulate_position_change(
            "u_1", [{"symbol": "AKBNK", "quantity_delta": 1}]
        )
        assert out["deltas"]["max_drawdown"] is None
        assert out["deltas"]["score"] == pytest.approx(-8.7)

    @pytest.mark.asyncio
    async def test_a_change_that_could_not_be_applied_is_reported(self, fake_backend):
        """Sessizce düşen bir değişiklik, kullanıcının tarif etmediği bir
        portföyü karşılaştırmak olurdu."""
        fake_backend.json("simulate", simulate_body(changes=[
            {"symbol": "YOK", "quantity_delta": 5, "applied": False,
             "note": "Enstrüman bulunamadı"},
        ]))
        out = await scenario_tools.simulate_position_change(
            "u_1", [{"symbol": "YOK", "quantity_delta": 5}]
        )
        assert out["applied"][0]["applied"] is False
        assert out["applied"][0]["note"] == "Enstrüman bulunamadı"

    @pytest.mark.asyncio
    async def test_a_missing_side_is_a_contract_violation(self, fake_backend):
        payload = simulate_body()
        del payload["hypothetical"]
        fake_backend.json("simulate", payload)
        with pytest.raises(ContractViolationError):
            await scenario_tools.simulate_position_change(
                "u_1", [{"symbol": "AKBNK", "quantity_delta": 1}]
            )

    @pytest.mark.asyncio
    async def test_a_non_object_side_is_refused(self, fake_backend):
        fake_backend.json("simulate", simulate_body(current=[35.5]))
        with pytest.raises(ContractViolationError):
            await scenario_tools.simulate_position_change(
                "u_1", [{"symbol": "AKBNK", "quantity_delta": 1}]
            )

    @pytest.mark.asyncio
    async def test_a_missing_metric_is_null_not_absent(self, fake_backend):
        fake_backend.json("simulate", simulate_body(current={"score": 1}))
        out = await scenario_tools.simulate_position_change(
            "u_1", [{"symbol": "AKBNK", "quantity_delta": 1}]
        )
        assert out["current"]["volatility"] is None
        assert set(out["current"]) == set(scenario_tools._SIDE_FIELDS)

    @pytest.mark.asyncio
    async def test_the_changes_are_sent_as_given(self, fake_backend):
        fake_backend.json("simulate", simulate_body())
        rows = [{"symbol": "AKBNK", "quantity_delta": 500}]
        await scenario_tools.simulate_position_change("u_1", rows, lookback="1M")
        assert fake_backend.body() == {"changes": rows, "lookback": "1M"}

    @pytest.mark.asyncio
    async def test_an_unreachable_backend_raises(self, fake_backend, no_sleep):
        fake_backend.fail("simulate")
        with pytest.raises(UpstreamUnavailableError):
            await scenario_tools.simulate_position_change(
                "u_1", [{"symbol": "AKBNK", "quantity_delta": 1}]
            )


class TestRegistration:
    def test_all_three_tools_are_attached(self):
        registered = []
        scenario_tools.register(
            type("FakeMCP", (), {"tool": lambda self: registered.append})()
        )
        assert registered == [
            scenario_tools.run_portfolio_scenario,
            scenario_tools.get_portfolio_stress_test,
            scenario_tools.simulate_position_change,
        ]
