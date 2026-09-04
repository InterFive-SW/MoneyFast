"""`/risk/scenario`, `/risk/stress` ve `/risk/simulate`'in MCP varyantı.

Her biri iki yüzeye hizmet ediyor: ekran oturumdan, sohbet yoldan gelen bir
kullanıcıyla. İkisi TEK bir yardımcıyı çağırıyor, dolayısıyla aynı portföy
için farklı bir duyarlılık söylemeleri mümkün değil -- `profile` ile
`profile/{user_id}` arasındaki desenin aynısı.

Yoldan kullanıcı alan uçlar `require_service_token` ile korunuyor: backend
aynı zamanda genel giriş noktası, dolayısıyla "yalnızca iç ağ" onun için
doğru değil ve korumasız bir uç, kullanıcı id'si tahmin eden herkese
başkasının portföyünü açardı.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_id
from app.main import app
from app.modules.investment import ai_service, market_service
from app.modules.risk import scenario

SCENARIO_URL = "/api/risk/scenario"
STRESS_URL = "/api/risk/stress"


def _closes(days: int, start: float = 100.0, steps=(0.01, -0.02, 0.03, -0.01)):
    base = date(2026, 1, 1)
    out, price = [], start
    for index in range(days):
        out.append((base + timedelta(days=index), price))
        price *= 1 + steps[index % len(steps)]
    return out


@pytest.fixture
def as_user(client):
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)


@pytest.fixture
def portfolio(mocker):
    """Tek TRY pozisyonu, yüz günlük geçmişiyle."""
    mocker.patch.object(
        market_service, "holdings",
        return_value=[{"symbol": "AKBNK", "name": "Akbank", "currency": "TRY",
                       "quantity": 100, "price": 60.0, "product_type": "stock",
                       "sector": "Financials"}],
    )
    mocker.patch.object(market_service, "latest_quotes", return_value={})
    mocker.patch.object(ai_service, "fx_rates", return_value={"TRY": 1.0})
    mocker.patch.object(ai_service, "holding_value", return_value=6000.0)
    mocker.patch.object(market_service, "candle_closes",
                        side_effect=lambda db, symbol, limit=260: _closes(100))


class TestScenarioEndpoint:
    def test_a_measured_factor_returns_beta_impact_and_a_sentence(
        self, as_user, portfolio
    ):
        body = as_user.post(
            SCENARIO_URL, json={"factor": "XU100", "shock_pct": 10}
        ).json()
        assert body["factor_name"] == "BIST 100"
        assert body["sensitivity"]["beta"] == pytest.approx(1.0)
        assert body["estimated_impact_pct"] == pytest.approx(10.0)
        assert body["statement"].endswith(f"{scenario.HEDGE_TR}.")

    def test_a_zero_shock_produces_no_impact(self, as_user, portfolio):
        """Sorulmayan bir şok, hesaplanmış bir etki üretmemeli."""
        body = as_user.post(
            SCENARIO_URL, json={"factor": "XU100", "shock_pct": 0}
        ).json()
        assert body["estimated_impact_pct"] == 0.0
        assert body["estimated_impact_value"] == 0.0

    def test_the_assumptions_are_returned_not_hidden(self, as_user, portfolio):
        """Gizlenmiş bir varsayım, olmayan bir kesinlik üretir."""
        body = as_user.post(
            SCENARIO_URL, json={"factor": "XU100", "shock_pct": 10}
        ).json()
        assert any("doğrusal" in a for a in body["assumptions"])

    def test_an_unmeasurable_factor_is_refused_with_the_measurable_ones(
        self, as_user, portfolio
    ):
        """Faiz: sistemde SERİ yok. Bir döviz faktörünü vekil koymak,
        uydurulmuş bir sayıyı ölçüm diye vermek olurdu."""
        response = as_user.post(
            SCENARIO_URL, json={"factor": "TR_POLICY_RATE", "shock_pct": 5}
        )
        assert response.status_code == 422
        assert "USDTRY" in response.json()["detail"]

    def test_the_factor_is_matched_case_insensitively(self, as_user, portfolio):
        assert as_user.post(
            SCENARIO_URL, json={"factor": "xu100", "shock_pct": 10}
        ).status_code == 200

    def test_a_shock_beyond_a_hundred_percent_is_refused(self, as_user, portfolio):
        """Bir günlük duyarlılığı oraya uzatmak, doğrusal varsayımı
        taşıyamayacağı yere taşımak olur."""
        assert as_user.post(
            SCENARIO_URL, json={"factor": "XU100", "shock_pct": 500}
        ).status_code == 422

    def test_an_empty_portfolio_is_refused_rather_than_measured(
        self, as_user, mocker
    ):
        mocker.patch.object(market_service, "holdings", return_value=[])
        mocker.patch.object(market_service, "latest_quotes", return_value={})
        mocker.patch.object(ai_service, "fx_rates", return_value={})
        response = as_user.post(
            SCENARIO_URL, json={"factor": "XU100", "shock_pct": 10}
        )
        assert response.status_code == 400

    def test_a_factor_with_no_shared_days_is_refused_not_zeroed(
        self, as_user, portfolio, mocker
    ):
        """Sıfır beta "bu faktör portföyü hiç etkilemiyor" diye okunur."""
        def closes(db, symbol, limit=260):
            if symbol == "XU100":
                return [(date(2020, 1, 1) + timedelta(days=i), 100.0 + i) for i in range(5)]
            return _closes(100)

        mocker.patch.object(market_service, "candle_closes", side_effect=closes)
        response = as_user.post(
            SCENARIO_URL, json={"factor": "XU100", "shock_pct": 10}
        )
        assert response.status_code == 400
        assert "ortak işlem günü" in response.json()["detail"]

    def test_a_lowercase_lookback_is_normalised_and_echoed(self, as_user, portfolio):
        """Model düzenli olarak "1y" yazıyor; reddetmek turu düşürürdü."""
        body = as_user.post(
            SCENARIO_URL, json={"factor": "XU100", "shock_pct": 10, "lookback": "3m"}
        ).json()
        assert body["lookback"] == "3M"

    def test_an_unknown_lookback_is_refused(self, as_user, portfolio):
        assert as_user.post(
            SCENARIO_URL, json={"factor": "XU100", "shock_pct": 10, "lookback": "365"}
        ).status_code == 422

    def test_an_anonymous_caller_is_refused(self, client):
        assert client.post(
            SCENARIO_URL, json={"factor": "XU100", "shock_pct": 10}
        ).status_code == 401


class TestStressEndpoint:
    def test_the_worst_days_are_real_days(self, as_user, portfolio):
        body = as_user.get(STRESS_URL).json()
        assert body["worst_days"]
        assert body["worst_days"][0]["return_pct"] < 0
        assert body["worst_days"][0]["date"].startswith("2026-")

    def test_every_measurable_factor_gets_a_replay_with_a_name(
        self, as_user, portfolio
    ):
        body = as_user.get(STRESS_URL).json()
        assert set(body["replays"]) == set(scenario.FACTORS)
        assert body["factor_names"]["XU100"] == "BIST 100"

    def test_an_unmeasurable_factor_is_absent_not_zero(
        self, as_user, portfolio, mocker
    ):
        """Sıfır, "o faktör portföyü hiç etkilemedi" demek olurdu."""
        def closes(db, symbol, limit=260):
            if symbol == "XAUUSD":
                return []
            return _closes(100)

        mocker.patch.object(market_service, "candle_closes", side_effect=closes)
        body = as_user.get(STRESS_URL).json()
        assert "XAUUSD" not in body["replays"]
        assert "XU100" in body["replays"]

    def test_an_empty_portfolio_returns_a_body_not_an_error(self, as_user, mocker):
        mocker.patch.object(market_service, "holdings", return_value=[])
        mocker.patch.object(market_service, "latest_quotes", return_value={})
        mocker.patch.object(ai_service, "fx_rates", return_value={})
        body = as_user.get(STRESS_URL).json()
        assert body["worst_days"] == []
        assert body["replays"] == {}
        assert body["observation_count"] == 0

    def test_an_anonymous_caller_is_refused(self, client):
        assert client.get(STRESS_URL).status_code == 401


class TestAgentEndpoints:
    """Yoldan kullanıcı alan varyantlar, servis jetonuyla korunuyor."""

    @pytest.fixture(autouse=True)
    def _token(self, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "secret")

    def _auth(self):
        return {"Authorization": "Bearer secret"}

    def test_the_scenario_variant_is_guarded(self, client):
        """Korumasız bir uç, kullanıcı id'si tahmin eden herkese başkasının
        portföyünü açardı."""
        assert client.post(
            f"{SCENARIO_URL}/user-1", json={"factor": "XU100", "shock_pct": 10}
        ).status_code == 401

    def test_the_stress_variant_is_guarded(self, client):
        assert client.get(f"{STRESS_URL}/user-1").status_code == 401

    def test_the_simulate_variant_is_guarded(self, client):
        assert client.post(
            "/api/risk/simulate/user-1",
            json={"changes": [{"symbol": "AKBNK", "quantity_delta": 1}]},
        ).status_code == 401

    def test_both_scenario_endpoints_answer_from_the_same_helper(
        self, as_user, portfolio
    ):
        """Ekran ile sohbetin aynı portföy için farklı bir duyarlılık
        söylemesi mümkün olmamalı."""
        payload = {"factor": "XU100", "shock_pct": 10}
        mine = as_user.post(SCENARIO_URL, json=payload).json()
        theirs = as_user.post(
            f"{SCENARIO_URL}/user-1", json=payload, headers=self._auth()
        ).json()
        assert mine == theirs

    def test_both_stress_endpoints_answer_from_the_same_helper(
        self, as_user, portfolio
    ):
        assert as_user.get(STRESS_URL).json() == as_user.get(
            f"{STRESS_URL}/user-1", headers=self._auth()
        ).json()

    def test_the_agent_scenario_reads_the_user_named_in_the_path(
        self, client, portfolio, mocker
    ):
        holdings = mocker.patch.object(
            market_service, "holdings",
            return_value=[{"symbol": "AKBNK", "currency": "TRY", "quantity": 1,
                           "price": 60.0, "product_type": "stock"}],
        )
        app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
        try:
            response = client.post(
                f"{SCENARIO_URL}/user-42", json={"factor": "XU100", "shock_pct": 10},
                headers=self._auth(),
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert response.status_code == 200
        assert holdings.call_args.kwargs["user_id"] == "user-42"

    def test_the_agent_stress_reads_the_user_named_in_the_path(
        self, client, portfolio, mocker
    ):
        holdings = mocker.patch.object(market_service, "holdings", return_value=[])
        app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
        try:
            response = client.get(f"{STRESS_URL}/user-9", headers=self._auth())
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert response.status_code == 200
        assert holdings.call_args.kwargs["user_id"] == "user-9"

    def test_the_agent_simulation_reads_the_user_named_in_the_path(
        self, client, portfolio, mocker
    ):
        holdings = mocker.patch.object(market_service, "holdings", return_value=[])
        app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
        try:
            response = client.post(
                "/api/risk/simulate/user-7",
                json={"changes": [{"symbol": "AKBNK", "quantity_delta": 1}]},
                headers=self._auth(),
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        # Pozisyonu olmayan bir kullanıcı 400 alıyor; önemli olan, yoldaki
        # kullanıcının okunmuş olması.
        assert response.status_code == 400
        assert holdings.call_args.kwargs["user_id"] == "user-7"
