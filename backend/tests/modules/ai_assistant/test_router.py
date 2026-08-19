"""Unit tests for app/modules/ai_assistant/router.py::chat_with_ai.

Bu endpoint tamamen kural tabanlı bir if/elif zinciri (DB yok, dış çağrı
yok). En riskli kısım: koşullar alt-dizgi eşleşmesiyle çalışıyor (`"al "`
`"satım"` gibi metin içinde de eşleşebilir), bu yüzden her dal için test
girdisi bilinçli seçildi — bir dalın kelimesi yanlışlıkla başka bir dalı da
tetiklemeyecek şekilde.

`no_sleep` fixture'ı (conftest.py) `asyncio.sleep(1.5)`'i no-op'a çevirir;
kullanılmazsa her test 1.5 saniye sürer.
"""

from __future__ import annotations


def test_chat_buy_intent_extracts_amount_and_builds_action_widget(client, no_sleep):
    response = client.post(
        "/api/ai_assistant/chat", json={"text": "aapl için 5 lot alım emri"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["context_topic"] == "AAPL İşlem"
    assert body["widget"]["type"] == "action"
    assert body["widget"]["payload"]["action"] == "buy"
    assert body["widget"]["payload"]["amount"] == 5
    assert body["widget"]["payload"]["actionId"] == "order_buy_aapl"


def test_chat_sell_intent_extracts_amount_and_builds_action_widget(client, no_sleep):
    response = client.post(
        "/api/ai_assistant/chat", json={"text": "aapl için 3 adet satım emri"}
    )

    body = response.json()
    assert body["widget"]["payload"]["action"] == "sell"
    assert body["widget"]["payload"]["amount"] == 3
    assert body["widget"]["payload"]["actionId"] == "order_sell_aapl"


def test_chat_order_intent_defaults_amount_to_ten_when_no_digits_present(
    client, no_sleep
):
    response = client.post(
        "/api/ai_assistant/chat", json={"text": "aapl için alım emri lütfen"}
    )

    assert response.json()["widget"]["payload"]["amount"] == 10


def test_chat_portfolio_keyword_triggers_rebalance_action_widget(client, no_sleep):
    response = client.post(
        "/api/ai_assistant/chat", json={"text": "portföyümü analiz eder misin"}
    )

    body = response.json()
    assert body["context_topic"] == "Portföy"
    assert body["widget"]["payload"]["actionId"] == "rebalance_10"


def test_chat_risk_keyword_also_triggers_rebalance_action_widget(client, no_sleep):
    response = client.post(
        "/api/ai_assistant/chat", json={"text": "risk durumumu göster"}
    )

    assert response.json()["context_topic"] == "Portföy"


def test_chat_apple_keyword_without_order_intent_returns_chart_widget(client, no_sleep):
    response = client.post(
        "/api/ai_assistant/chat", json={"text": "apple hissesi nasıl gidiyor"}
    )

    body = response.json()
    assert body["context_topic"] == "AAPL"
    assert body["widget"]["type"] == "chart"
    assert body["widget"]["payload"]["title"] == "AAPL Son 5 Günlük Performans"


def test_chat_bist_keyword_returns_bist_chart_widget(client, no_sleep):
    response = client.post(
        "/api/ai_assistant/chat", json={"text": "bist 100 bugün nasıl"}
    )

    body = response.json()
    assert body["context_topic"] == "BIST 100"
    assert body["widget"]["payload"]["title"] == "BIST 100 Gün İçi Performans"


def test_chat_unmatched_text_returns_default_response_without_widget(client, no_sleep):
    response = client.post("/api/ai_assistant/chat", json={"text": "merhaba nasılsın"})

    assert response.status_code == 200
    body = response.json()
    assert body["context_topic"] is None
    assert body["widget"] is None
    assert "standart bir analiz" in body["text"]


def test_chat_response_always_includes_four_fixed_thoughts(client, no_sleep):
    response = client.post("/api/ai_assistant/chat", json={"text": "merhaba"})

    assert len(response.json()["thoughts"]) == 4


def test_chat_missing_text_field_returns_422(client, no_sleep):
    response = client.post("/api/ai_assistant/chat", json={})

    assert response.status_code == 422


def test_ai_assistant_health_reports_module_name(client):
    response = client.get("/api/ai_assistant/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": "ai_assistant"}
