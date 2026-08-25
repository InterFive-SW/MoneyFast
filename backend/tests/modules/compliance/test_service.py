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
