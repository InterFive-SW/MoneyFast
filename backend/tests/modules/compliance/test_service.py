"""Which disclosures a draft actually needs.

The rule these tests pin down: a disclosure attaches to a financial claim, not
to every reply. See `service.has_financial_content` for why.
"""

from __future__ import annotations

import pytest

from app.modules.compliance import service


class TestDisclaimerIsConditional:
    """The general disclaimer used to be appended to every reply — greetings
    and error messages included. Boilerplate under text that asserts nothing
    trains the reader to skip the notice on the answers where it matters.
    """

    def _disclosures(self, draft, tools=None, personal=False, proposal=False):
        return [
            entry["disclosure_id"]
            for entry in service.required_disclosures(draft, personal, proposal, tools or [])
        ]

    def test_a_greeting_carries_no_disclaimer(self):
        assert self._disclosures("Merhaba! Size nasıl yardımcı olabilirim?") == []

    def test_a_data_failure_message_carries_no_disclaimer(self):
        """A failed tool never reaches tools_used, and "I could not reach the
        data" makes no financial claim to disclaim."""
        assert self._disclosures("Verilere şu anda ulaşamadım, tekrar deneyeyim mi?") == []

    def test_a_refusal_carries_no_disclaimer(self):
        assert self._disclosures("Para transferi henüz desteklenmiyor.") == []

    @pytest.mark.parametrize(
        "draft",
        [
            "THYAO 301,25 TL seviyesinde.",
            "Portföyünüz %12 değer kazandı.",
            "Toplam 1.063.324,47 TL.",
            "120 adet hisseniz var.",
        ],
    )
    def test_any_figure_pulls_the_disclaimer_back_in(self, draft):
        """Broad on purpose: a false positive costs one line, a false negative
        omits a legally required notice."""
        assert "DISC-GENERAL" in self._disclosures(draft)

    def test_a_tool_run_makes_the_turn_financial_even_without_figures(self):
        assert "DISC-GENERAL" in self._disclosures(
            "Bu kriterlere uyan enstrüman bulunamadı.", tools=["get_market_data"]
        )

    def test_a_transaction_proposal_always_carries_it(self):
        assert "DISC-GENERAL" in self._disclosures("İşlem hazırlandı.", proposal=True)

    def test_personal_data_always_carries_it(self):
        assert "DISC-GENERAL" in self._disclosures("Hesabınız görüntülendi.", personal=True)


class TestDelayedDisclosureCoversPrices:
    def test_a_price_answer_gets_the_delay_notice(self):
        """get_market_data is the tool that RETURNS is_delayed, yet a bare
        price answer was going out with no delay disclosure at all."""
        ids = [
            entry["disclosure_id"]
            for entry in service.required_disclosures(
                "THYAO 301,25 TL.", False, False, ["get_market_data"]
            )
        ]
        assert "DISC-DELAYED" in ids


class TestRoutingIsNotFinancialContent:
    def test_the_router_tool_alone_does_not_pull_in_a_disclaimer(self):
        """`classify_and_route_intent` is recorded on every turn, including
        greetings. Treating it as "a tool ran" would make the disclaimer
        unconditional again through the back door."""
        ids = [
            entry["disclosure_id"]
            for entry in service.required_disclosures(
                "Merhaba! Size nasıl yardımcı olabilirim?",
                False,
                False,
                ["classify_and_route_intent"],
            )
        ]
        assert ids == []

    def test_a_real_tool_alongside_the_router_still_counts(self):
        ids = [
            entry["disclosure_id"]
            for entry in service.required_disclosures(
                "Sonuç bulunamadı.",
                False,
                False,
                ["classify_and_route_intent", "get_market_data"],
            )
        ]
        assert "DISC-GENERAL" in ids


class TestUnhedgedDirectionIsBlocked:
    """GUA-003 — the gate that pays for the prompt's one relaxation.

    The system prompt now permits a CONDITIONAL forward reading attached to a
    computed indicator ("bu görünüm sürdüğü sürece ... beklenebilir — ancak
    geçmiş fiyat hareketi geleceği belirlemez"). A prompt is advice; this rule
    is what makes the boundary real. GUA-002 only ever caught "kesinlikle
    yükselecek", so a bare "yükselecek" was already getting through before the
    relaxation gave the model a reason to write one.
    """

    def _rule_ids(self, draft):
        from app.modules.compliance import rules

        return [v["rule_id"] for v in rules.find_violations(draft, "NORMAL", False)]

    @pytest.mark.parametrize(
        "draft",
        [
            "Bu hisse yükselecek.",
            "Önümüzdeki ay artacak.",
            "Yakında ikiye katlanacak.",
            "Size kazandıracak.",
        ],
    )
    def test_a_bare_forward_claim_is_caught(self, draft):
        assert "GUA-003" in self._rule_ids(draft)

    def test_the_relayed_technical_reading_passes(self):
        """The exact sentence `technicals.narrate` produces. If this rule
        blocked it, the feature it guards could not ship."""
        from app.modules.market import technicals

        draft = technicals.narrate("AKBNK", {
            "trend": "UPTREND", "last_close": 100.0, "pct_from_sma_50": 8.2,
            "up_days_recent": 14, "recent_window": 20,
            "week52_position_pct": 72.5,
        })
        assert self._rule_ids(draft) == []

    def test_a_downtrend_reading_passes_too(self):
        from app.modules.market import technicals

        draft = technicals.narrate("XYZ", {
            "trend": "DOWNTREND", "last_close": 10.0, "pct_from_sma_50": -6.5,
        })
        assert self._rule_ids(draft) == []

    def test_describing_the_present_was_never_the_problem(self):
        assert self._rule_ids("Teknik olarak yükseliş eğiliminde.") == []
        assert self._rule_ids("50 günlük ortalamasının %8,2 üzerinde.") == []

    def test_a_refusal_that_quotes_the_verb_is_not_a_violation(self):
        """"Kimse size kazandıracak diyemez" REJECTS the claim; flagging it
        would strip the sentence whose whole job is to refuse."""
        assert self._rule_ids("Kimse size kazandıracak diyemez.") == []
        assert self._rule_ids("Yükselecek mi diye soruyorsanız kimse bilemez.") == []

    def test_dropping_the_caveat_turns_a_permitted_sentence_into_a_blocked_one(self):
        """The caveat is not decoration. Without it the same clause is exactly
        the claim the rule exists to stop."""
        from app.modules.market import technicals

        permitted = technicals.narrate("AKBNK", {
            "trend": "UPTREND", "last_close": 100.0, "pct_from_sma_50": 8.2,
        })
        assert self._rule_ids(permitted) == []
        assert self._rule_ids("AKBNK yükselecek.") != []
