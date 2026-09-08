"""Chat widget construction.

The security property under test: a widget is a projection of data a tool
actually returned. The model contributes nothing to it. A confirm button
carrying a proposal id that was never staged would let a user authorise an
order that does not exist, so most of these tests are about REFUSING to build
one.
"""

from __future__ import annotations

import pytest

import widgets


def staged_proposal(**overrides):
    payload = {
        "proposal_id": "PROP-ABC123",
        "status": "PENDING_USER_CONFIRMATION",
        "confirmation_required": True,
        "expires_at": "2026-08-20T12:15:00Z",
        "summary": {
            "transaction_type": "BUY",
            "symbol": "TEST-THYAO",
            "quantity": 10,
            "order_type": "MARKET",
        },
        "estimate": {"net_amount": 2959.65, "currency": "TRY", "price_certainty": "INDICATIVE"},
    }
    payload.update(overrides)
    return payload


def state_for(agent: str, data, status: str = "OK", target: str | None = None):
    return {
        "target_agent": agent if target is None else target,
        "specialist_output": {"agent": agent, "status": status, "data": data},
    }


PORTFOLIO = {
    "as_of": "2026-08-20T09:00:00Z",
    "base_currency": "TRY",
    "is_delayed": False,
    "totals": {"total_market_value": 555035.0, "total_unrealized_pnl": 53865.0},
    "positions": [
        {
            "symbol": "TEST-THYAO", "quantity": 120.0, "avg_cost": 280.0,
            "last_price": 295.5, "market_value": 35460.0,
            "unrealized_pnl": 1860.0, "unrealized_pnl_pct": 0.0553,
        }
    ],
}


class TestActionWidget:
    def test_staged_proposal_becomes_a_confirmable_widget(self):
        widget, topic = widgets.build(state_for("TRANSACTION_AGENT", staged_proposal()))
        assert widget["type"] == "action"
        assert widget["payload"]["proposalId"] == "PROP-ABC123"
        assert widget["payload"]["action"] == "buy"
        assert widget["payload"]["amount"] == 10
        assert topic == "TEST-THYAO"

    def test_action_id_is_the_real_proposal_not_a_synthetic_order(self):
        """The confirm endpoint validates against this value. A synthetic id
        would 404, and a guessable one would be worse."""
        widget, _ = widgets.build(state_for("TRANSACTION_AGENT", staged_proposal()))
        assert widget["payload"]["actionId"] == "PROP-ABC123"

    def test_message_carries_the_estimated_cost_in_turkish_format(self):
        widget, _ = widgets.build(state_for("TRANSACTION_AGENT", staged_proposal()))
        assert "2.959,65 TRY" in widget["payload"]["message"]

    def test_sell_is_labelled_as_a_sell(self):
        proposal = staged_proposal()
        proposal["summary"]["transaction_type"] = "SELL"
        widget, _ = widgets.build(state_for("TRANSACTION_AGENT", proposal))
        assert widget["payload"]["action"] == "sell"
        assert "Satım" in widget["payload"]["message"]

    def test_turkish_transaction_verb_is_understood(self):
        proposal = staged_proposal()
        proposal["summary"]["transaction_type"] = "ALIŞ"
        widget, _ = widgets.build(state_for("TRANSACTION_AGENT", proposal))
        assert widget["payload"]["action"] == "buy"

    def test_missing_estimate_omits_the_cost_rather_than_showing_zero(self):
        widget, _ = widgets.build(
            state_for("TRANSACTION_AGENT", staged_proposal(estimate=None))
        )
        assert "yaklaşık" not in widget["payload"]["message"]


class TestActionWidgetRefusals:
    def test_rejected_proposal_gets_no_confirm_button(self):
        """A refusal is a message, not something to authorise."""
        widget, _ = widgets.build(
            state_for("TRANSACTION_AGENT", staged_proposal(status="REJECTED_VALIDATION"))
        )
        assert widget is None

    def test_incomplete_proposal_gets_no_confirm_button(self):
        widget, _ = widgets.build(
            state_for("TRANSACTION_AGENT", staged_proposal(status="REQUIRES_ADDITIONAL_INPUT"))
        )
        assert widget is None

    def test_proposal_without_the_confirmation_assertion_is_refused(self):
        """confirmation_required is a contract constant. A proposal reaching
        the user without it is indistinguishable from a completed order."""
        widget, _ = widgets.build(
            state_for("TRANSACTION_AGENT", staged_proposal(confirmation_required=False))
        )
        assert widget is None

    def test_proposal_without_an_id_is_refused(self):
        widget, _ = widgets.build(
            state_for("TRANSACTION_AGENT", staged_proposal(proposal_id=None))
        )
        assert widget is None

    def test_needs_input_status_produces_nothing(self):
        widget, topic = widgets.build(
            {"specialist_output": {"agent": "TRANSACTION_AGENT", "status": "NEEDS_INPUT"}}
        )
        assert (widget, topic) == (None, None)


class TestPortfolioWidget:
    def test_positions_become_a_table(self):
        widget, topic = widgets.build(state_for("PORTFOLIO_AGENT", PORTFOLIO))
        assert widget["type"] == "portfolio"
        assert widget["payload"]["total_value"] == 555035.0
        assert len(widget["payload"]["positions"]) == 1
        # No context topic: the table is already rendered inline, and the
        # panel would open showing a live price for "Portföy", which is not an
        # instrument.
        assert topic is None

    def test_freshness_travels_with_the_figures(self):
        """The contract forbids restating quantities without their as_of and
        is_delayed context; a widget that dropped them would do exactly that."""
        widget, _ = widgets.build(state_for("PORTFOLIO_AGENT", PORTFOLIO))
        assert widget["payload"]["as_of"] == "2026-08-20T09:00:00Z"
        assert widget["payload"]["is_delayed"] is False

    def test_empty_portfolio_draws_no_table(self):
        widget, _ = widgets.build(state_for("PORTFOLIO_AGENT", {"positions": [], "totals": {}}))
        assert widget is None

    def test_missing_position_fields_default_rather_than_raise(self):
        widget, _ = widgets.build(
            state_for("PORTFOLIO_AGENT", {"positions": [{"symbol": "X"}], "totals": {}})
        )
        assert widget["payload"]["positions"][0] == {
            "symbol": "X",
            # Defaults to lira when the contract omits it, like every other
            # field here — never guessed from the symbol.
            "instrument_currency": "TRY", "quantity": 0.0, "avg_cost": 0.0, "last_price": 0.0,
            "market_value": 0.0, "unrealized_pnl": 0.0, "unrealized_pnl_pct": 0.0,
        }


class TestNoWidgetCases:
    @pytest.mark.parametrize(
        "agent", ["MARKET_RESEARCH_AGENT", "RISK_STRATEGY_AGENT", "EDUCATION_AGENT", "HUMAN_HANDOFF"]
    )
    def test_agents_without_a_widget_return_none(self, agent):
        assert widgets.build(state_for(agent, {"anything": 1})) == (None, None)

    @pytest.mark.parametrize("status", ["EMPTY", "ERROR", "HANDOFF"])
    def test_non_ok_status_never_renders(self, status):
        """EMPTY, ERROR and HANDOFF all mean there is no payload worth
        showing. The prose already explains why."""
        assert widgets.build(state_for("PORTFOLIO_AGENT", PORTFOLIO, status=status)) == (None, None)

    def test_turn_without_a_specialist_output(self):
        assert widgets.build({}) == (None, None)

    def test_null_data_does_not_raise(self):
        assert widgets.build(state_for("PORTFOLIO_AGENT", None)) == (None, None)


class TestTurkishAmountFormatting:
    @pytest.mark.parametrize(
        "value,expected",
        [(1250.5, "1.250,50"), (2959.65, "2.959,65"), (1234567.891, "1.234.567,89"), (0.5, "0,50")],
    )
    def test_thousands_dot_decimal_comma(self, value, expected):
        """locale would need tr_TR installed in the image; when it is missing
        Python silently falls back to en_US, which reads as a hundredfold
        error to a Turkish user."""
        assert widgets._tr_amount(value) == expected


class TestStaleStateGuard:
    """The graph checkpoints on thread_id, so a specialist_output left by an
    earlier turn can survive into one that ran no tool. The observed symptom
    was a refusal message rendered with the previous turn's transaction
    confirm button attached."""

    def test_output_from_a_different_agent_is_not_rendered(self):
        stale = state_for("TRANSACTION_AGENT", staged_proposal(), target="EDUCATION_AGENT")
        assert widgets.build(stale) == (None, None)

    def test_matching_agent_still_renders(self):
        widget, _ = widgets.build(
            state_for("TRANSACTION_AGENT", staged_proposal(), target="TRANSACTION_AGENT")
        )
        assert widget["type"] == "action"

    def test_absent_target_agent_renders_nothing(self):
        """A turn that never routed has nothing to show."""
        assert widgets.build(
            {"specialist_output": {"agent": "PORTFOLIO_AGENT", "status": "OK", "data": PORTFOLIO}}
        ) == (None, None)


class TestTransferWidget:
    """A transfer is not a trade. It used to render as "Satım" with a blank
    ticker, because the direction was computed as "buy, or else sell"."""

    def _state(self, summary, estimate=None):
        return {
            "target_agent": "TRANSACTION_AGENT",
            "specialist_output": {
                "agent": "TRANSACTION_AGENT",
                "status": "OK",
                "data": {
                    "proposal_id": "PROP-1",
                    "status": "PENDING_USER_CONFIRMATION",
                    "confirmation_required": True,
                    "summary": summary,
                    "estimate": estimate or {"net_amount": 200.0, "currency": "TRY"},
                },
            },
        }

    def test_a_transfer_names_the_destination_not_a_ticker(self):
        widget, topic = widgets.build(self._state({
            "transaction_type": "TRANSFER",
            "destination_account_id": "1000000000002",
        }))
        assert "1000000000002" in widget["payload"]["message"]
        assert "Satım" not in widget["payload"]["message"]
        assert widget["payload"]["action"] == "transfer"
        # A transfer has no instrument, so no context panel: the panel shows a
        # live price and instrument news, and a transfer has neither.
        assert topic is None

    def test_a_sell_still_reads_as_a_sale(self):
        widget, _ = widgets.build(self._state({
            "transaction_type": "SELL", "symbol": "ASELS", "quantity": 10,
        }))
        assert "Satım" in widget["payload"]["message"]
        assert widget["payload"]["action"] == "sell"

    def test_a_buy_still_reads_as_a_purchase(self):
        widget, _ = widgets.build(self._state({
            "transaction_type": "BUY", "symbol": "ASELS", "quantity": 10,
        }))
        assert "Alım" in widget["payload"]["message"]
        assert widget["payload"]["action"] == "buy"

    def test_an_unrecognised_type_is_not_displayed_as_a_sale(self):
        """The old fallback rendered anything unknown as "Satım" — a type
        nobody handled was shown to the user as a sale of their holdings."""
        widget, _ = widgets.build(self._state({
            "transaction_type": "SUBSCRIBE", "symbol": "XYZ", "quantity": 1,
        }))
        assert "Satım" not in widget["payload"]["message"]
        assert widget["payload"]["action"] == "unknown"


class TestContextTopic:
    """The topic drives a side panel that shows a live price and news for one
    instrument. Anything that is not a ticker must not open it — the panel used
    to appear mid-transaction showing a price for the word "Portföy"."""

    def _action_state(self, summary):
        return {
            "target_agent": "TRANSACTION_AGENT",
            "specialist_output": {
                "agent": "TRANSACTION_AGENT", "status": "OK",
                "data": {
                    "proposal_id": "PROP-1",
                    "status": "PENDING_USER_CONFIRMATION",
                    "confirmation_required": True,
                    "summary": summary,
                    "estimate": {"net_amount": 100.0, "currency": "TRY"},
                },
            },
        }

    def test_a_real_ticker_becomes_the_topic(self):
        _, topic = widgets.build(self._action_state({
            "transaction_type": "BUY", "symbol": "ASELS", "quantity": 1,
        }))
        assert topic == "ASELS"

    def test_a_trade_without_a_symbol_opens_no_panel(self):
        _, topic = widgets.build(self._action_state({
            "transaction_type": "BUY", "quantity": 1,
        }))
        assert topic is None


class TestRebalanceWidget:
    """Dengeleme listesi widget'ı, ARAÇ YÜKÜNDEN deterministik.

    Buradaki gerekçe modülün geri kalanından güçlü: bu widget birden çok
    işlem satırı taşıyor, yani widget JSON'u üretebilen bir model uydurulmuş
    bir işlem LİSTESİ üretebilir ve kullanıcı onu tıklanabilir bir yüzey
    olarak görür.
    """

    ROW = {
        "symbol": "NVDA", "side": "SELL", "quantity": 26.0, "amount": 281371.44,
        "bucket": "ABD Hisse",
        "statement": "NVDA için 26 adet satışın karşılığı 281.371,44 TRY.",
        "rationale": [
            {"kind": "RISK_CONTRIBUTION", "value": 0.40,
             "text": "Portföy oynaklığının %40,2'lik kısmını bu pozisyon üretiyor."},
        ],
    }

    def _state(self, data):
        return {
            "target_agent": "RISK_STRATEGY_AGENT",
            "specialist_output": {
                "status": "OK", "agent": "RISK_STRATEGY_AGENT", "data": data
            },
        }

    def _data(self, **overrides):
        data = {
            "gate": {"open": True, "reason": "ok"},
            "disclaimer": "Bu liste yatırım tavsiyesi değildir.",
            "bandStatement": "Hedef kendi belirlediğiniz dağılıma göre kuruldu.",
            "rows": [dict(self.ROW)],
        }
        data.update(overrides)
        return data

    def test_a_plan_becomes_a_widget(self):
        widget, topic = widgets.build(self._state(self._data()))
        assert widget["type"] == "rebalance"
        assert topic is None
        assert widget["payload"]["rows"][0]["symbol"] == "NVDA"

    def test_every_row_carries_its_reasons_as_plain_text(self):
        widget, _ = widgets.build(self._state(self._data()))
        assert widget["payload"]["rows"][0]["rationale"] == [
            "Portföy oynaklığının %40,2'lik kısmını bu pozisyon üretiyor."
        ]

    def test_a_row_without_a_reason_is_not_drawn(self):
        """Sebebi görünmeyen bir satırın yanında bir "Uygula" düğmesi, tam
        olarak kaldırılan yasağın engellediği şey."""
        data = self._data(rows=[{**self.ROW, "rationale": []}])
        assert widgets.build(self._state(data)) == (None, None)

    def test_a_non_object_row_is_dropped(self):
        data = self._data(rows=["NVDA", dict(self.ROW)])
        widget, _ = widgets.build(self._state(data))
        assert len(widget["payload"]["rows"]) == 1

    def test_a_closed_gate_draws_nothing(self):
        """Boş bir tablo, yapılacak bir şey varmış gibi görünürdü; nedeni
        zaten metinde yazılı."""
        data = self._data(gate={"open": False, "reason": "Testi tamamlayın."})
        assert widgets.build(self._state(data)) == (None, None)

    def test_an_empty_list_draws_nothing(self):
        assert widgets.build(self._state(self._data(rows=[]))) == (None, None)

    def test_the_disclaimer_and_the_band_sentence_travel(self):
        widget, _ = widgets.build(self._state(self._data()))
        assert "yatırım tavsiyesi değildir" in widget["payload"]["disclaimer"]
        assert "kendi belirlediğiniz" in widget["payload"]["band_statement"]

    def test_risk_metrics_alone_draw_no_widget(self):
        """Çekinceli sayılardan oluşan bir tablo, widget'a çevrildiğinde
        çekincelerini kaybediyor."""
        state = self._state({"metrics": {"volatility_annualized": 0.31}})
        assert widgets.build(state) == (None, None)


class TestNewsImpactWidget:
    """Haber okumasının ÖLÇÜLEN zemini; yorum METİNDE kalıyor.

    Bir widget, metnin yanında ama metinden BAĞIMSIZ okunuyor: kullanıcı
    tabloyu okuyup paragrafı atlayabilir. O yüzden tabloda duran her şey tek
    başına doğru olmak zorunda -- bir kanaat cümlesi bu koşulu sağlamıyor,
    çünkü çekincesi paragrafta kalıyor.
    """

    DATA = {
        "window_days": 90,
        "symbols": [{
            "symbol": "AKBNK", "sector": "Financial Services",
            "news_count": 114, "filing_count": 25,
            "price": {"recent_move_pct": 1.11, "typical_move_pct": 4.42,
                      "window_days": 5},
            "fundamentals": {"pe_ratio": 4.2}, "articles": [],
        }],
        "coverage": {"articles": 200, "filings": 148, "feed_articles": 52,
                     "symbols": 16, "symbols_with_news": 15,
                     "symbols_omitted": 11},
    }

    def _state(self, data):
        return {
            "target_agent": "PORTFOLIO_AGENT",
            "specialist_output": {
                "status": "OK", "agent": "PORTFOLIO_AGENT", "data": data
            },
        }

    def test_a_fact_package_becomes_a_widget(self):
        widget, topic = widgets.build(self._state(self.DATA))
        assert widget["type"] == "news_impact" and topic is None
        assert widget["payload"]["rows"][0]["symbol"] == "AKBNK"

    def test_both_price_figures_are_drawn_together(self):
        """Bir hareket ancak KENDİ aralığına karşı büyük; tek başına
        gösterilen bir yüzde, okuyucunun onu kendi ölçeğiyle yorumlamasına
        bırakılıyor demektir."""
        widget, _ = widgets.build(self._state(self.DATA))
        row = widget["payload"]["rows"][0]
        assert row["recent_move_pct"] == 1.11
        assert row["typical_move_pct"] == 4.42

    def test_an_unmeasured_price_stays_null(self):
        data = {**self.DATA, "symbols": [{
            **self.DATA["symbols"][0],
            "price": {"recent_move_pct": None, "typical_move_pct": None},
        }]}
        row = widgets.build(self._state(data))[0]["payload"]["rows"][0]
        assert row["recent_move_pct"] is None

    def test_the_omitted_count_is_drawn(self):
        """Tabloyu tek başına okuyan biri, listelenenlerin portföyün tamamı
        olduğunu sanmamalı."""
        widget, _ = widgets.build(self._state(self.DATA))
        assert widget["payload"]["coverage"]["symbols_omitted"] == 11
        assert widget["payload"]["coverage"]["symbols"] == 16

    def test_the_source_split_is_drawn(self):
        widget, _ = widgets.build(self._state(self.DATA))
        assert widget["payload"]["coverage"]["filings"] == 148
        assert widget["payload"]["coverage"]["feed_articles"] == 52

    def test_no_judgement_reaches_the_widget(self):
        """Yorum metinde, uygunluk kapısından geçmiş hâliyle duruyor."""
        widget, _ = widgets.build(self._state(self.DATA))
        import json as _json

        flat = _json.dumps(widget, ensure_ascii=False).lower()
        for banned in ("olumlu", "olumsuz", "risk", "öneri", "tavsiye"):
            assert banned not in flat

    def test_an_empty_package_draws_nothing(self):
        assert widgets.build(self._state({**self.DATA, "symbols": []})) == (None, None)

    def test_a_non_object_row_is_dropped(self):
        data = {**self.DATA, "symbols": ["AKBNK", self.DATA["symbols"][0]]}
        assert len(widgets.build(self._state(data))[0]["payload"]["rows"]) == 1

    def test_a_positions_payload_still_draws_the_portfolio_widget(self):
        """İki ayrı yük, iki ayrı widget: `coverage` varsa haber paketi."""
        widget, _ = widgets.build(self._state({
            "positions": [{"symbol": "AKBNK", "quantity": 10}],
            "totals": {"total_market_value": 1000.0},
        }))
        assert widget["type"] == "portfolio"
