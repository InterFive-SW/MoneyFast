"""Unit tests for app/modules/investment/router.py.

Router'ın tamamı mock veri döndüren tek satırlık gövdelerden oluşuyor
(if/else, DB, Depends yok) — bu yüzden "sözleşme testi" yaklaşımı: her
endpoint 200 dönmeli ve yanıt Pydantic response_model şeklini karşılamalı.
Bu yaklaşım DB entegrasyonu geldiğinde de değerini korur: endpoint'in
gövdesi mock'tan gerçek sorguya dönse bile, şema değişmediği sürece bu
testler geçmeye devam eder; şema değişirse bilinçli olarak kırılır.
"""

from __future__ import annotations

import pytest

LIST_ENDPOINTS = [
    "/api/investment/positions",
    "/api/investment/orders",
    "/api/investment/asset-allocation",
    "/api/investment/dividends",
    "/api/investment/sector-allocation",
    "/api/investment/heatmap",
]


@pytest.mark.parametrize("path", LIST_ENDPOINTS)
def test_list_endpoint_returns_200_with_nonempty_list(client, path):
    response = client.get(path)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) > 0


def test_portfolio_summary_returns_balance_contract(client):
    response = client.get("/api/investment/portfolio/summary")

    assert response.status_code == 200
    assert set(response.json()) == {"totalTRY", "totalUSD", "breakdown"}


def test_portfolio_chart_returns_all_five_range_keys(client):
    response = client.get("/api/investment/portfolio/chart")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"Gün", "Hafta", "Ay", "3 Ay", "Yıl"}
    for candles in body.values():
        assert isinstance(candles, list) and len(candles) > 0
        assert set(candles[0]) >= {"time", "open", "high", "low", "close"}


def test_watchlist_returns_bist_us_crypto_groups(client):
    response = client.get("/api/investment/watchlist")

    assert response.status_code == 200
    assert set(response.json()) == {"bist", "us", "crypto"}


def test_top_movers_returns_gainers_and_losers_groups(client):
    response = client.get("/api/investment/top-movers")

    assert response.status_code == 200
    assert set(response.json()) == {"gainers", "losers"}


def test_orders_have_only_literal_status_and_type_values(client):
    response = client.get("/api/investment/orders")

    for order in response.json():
        assert order["status"] in {"Bekliyor", "Gerçekleşti", "İptal"}
        assert order["type"] in {"Alış", "Satış"}


def test_investment_health_reports_module_name(client):
    response = client.get("/api/investment/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": "investment"}


def test_propose_order_ignores_request_body_and_returns_fixed_contract(client):
    response = client.post(
        "/api/investment/orders/propose",
        json={"asset": "TEST-THYAO", "action": "Alış", "amount": 13},
    )

    assert response.status_code == 200
    assert response.json() == {"order_id": "TEST-ORDER-123", "status": "proposed"}


def test_propose_order_missing_field_returns_422(client):
    response = client.post(
        "/api/investment/orders/propose", json={"asset": "TEST-THYAO"}
    )

    assert response.status_code == 422


def test_confirm_order_echoes_order_id_in_message(client):
    response = client.post(
        "/api/investment/orders/confirm",
        json={"order_id": "TEST-ORDER-999", "action": "Alış"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed"
    assert "TEST-ORDER-999" in body["message"]


def test_confirm_order_missing_field_returns_422(client):
    response = client.post("/api/investment/orders/confirm", json={"action": "Alış"})

    assert response.status_code == 422
