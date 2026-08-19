"""Unit tests for app/modules/market/router.py."""

from __future__ import annotations


def test_market_tickers_returns_four_known_symbols(client):
    response = client.get("/api/market/tickers")

    assert response.status_code == 200
    symbols = {ticker["symbol"] for ticker in response.json()}
    assert symbols == {"USD/TRY", "EUR/TRY", "XAU/TRY", "BIST100"}


def test_market_news_strips_category_field_not_declared_in_schema(client):
    """MOCK_NEWS kayıtlarında `category` alanı var ama `NewsItem` şemasında
    yok; `response_model` bu alanı yanıttan siziyor. Bu davranışı bilinçli
    olarak sabitliyoruz — biri şemaya `category` eklerse bu test bilinçli
    olarak kırılıp güncellenmeyi hatırlatır."""
    response = client.get("/api/market/news")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 6
    for item in body:
        assert "category" not in item
        assert item["sentiment"] in {"positive", "negative", "neutral"}


def test_market_health_reports_module_name(client):
    response = client.get("/api/market/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": "market"}
