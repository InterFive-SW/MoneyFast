"""`get_rebalance_plan` — sözleşme v2.24.

Bu araç, sistemin "tavsiye üretme" yasağının kaldırıldığı tek yer. Bu
dosyanın asıl işi o kaldırmanın karşılıksız olmadığını çivilemek: gerekçesi
olmayan bir satır burada REDDEDİLİYOR, ve reddedilmesi bir tercih değil,
aracın var olma dayanağı.
"""

from __future__ import annotations

import pytest

import rebalance_tools as portfolio_tools
from backend_client import ContractViolationError

pytestmark = pytest.mark.asyncio


class TestRebalancePlanTool:
    """v2.24. Satırlar artık taşınıyor -- ama YALNIZCA gerekçeleriyle.

    v2.22'de satırlar bilerek dışarıda bırakılmıştı ve sebebi ölçülmüştü:
    model onları bir alım-satım tablosuna çeviriyordu. Değişen şey satırların
    kendisi -- her satır onu üreten ölçümü yanında taşıyor ve gerekçesi
    olmayan satır backend'de hiç üretilmiyor. Koruma "göndermemek"ten
    "sayısıyla birlikte göndermek"e geçti, ve bu sınıf o sayının gerçekten
    zorunlu olduğunu çiviliyor.
    """

    BODY = {
        "gate": {"open": True, "reason": "Uygunluk testi tamamlanmış."},
        "disclaimer": "Bu liste yatırım tavsiyesi değildir.",
        "hasTarget": True,
        "statement": "Sapma ölçüldü.",
        "bandStatement": "Hedef kendi belirlediğiniz dağılıma göre kuruldu.",
        "summary": "Dengeleme ekranında 1 satış satırı var.",
        "measuredLevel": "Orta",
        "declaredTolerance": "Yüksek",
        "bindingBand": "Orta",
        "rows": [{
            "symbol": "THYAO", "side": "SELL", "label": "BIST Hisse",
            "quantity": 12, "price": 300.0, "amount_base": 3600.0,
            "residual_base": 12.5,
            "statement": "THYAO için 12 adet satışın karşılığı 3.600,00 TRY.",
            "rationale": [
                {"kind": "RISK_CONTRIBUTION", "value": 0.31,
                 "text": "Portföy oynaklığının %31,0'lik kısmını bu pozisyon üretiyor."},
            ],
        }],
        "unresolved": [{"label": "Altın", "reason": "pozisyonunuz yok",
                        "gap_amount": -5000}],
    }

    @pytest.mark.asyncio
    async def test_it_asks_the_service_endpoint(self, mocker):
        called = {}

        async def fake(method, path, tool=None, **kw):
            called.update({"method": method, "path": path})
            return dict(self.BODY)

        mocker.patch.object(portfolio_tools.backend_client, "request", side_effect=fake)
        await portfolio_tools.get_rebalance_plan("u-1")
        assert called["path"] == "/investment/rebalance/plan/u-1"
        assert called["method"] == "GET"

    def test_a_body_without_the_required_keys_is_refused(self):
        with pytest.raises(ContractViolationError):
            portfolio_tools._normalize_rebalance({"summary": "x"})

    def test_a_row_travels_with_its_rationale(self):
        out = portfolio_tools._normalize_rebalance(dict(self.BODY))
        row = out["rows"][0]
        assert row["symbol"] == "THYAO" and row["side"] == "SELL"
        assert row["rationale"][0]["kind"] == "RISK_CONTRIBUTION"
        assert row["rationale"][0]["value"] == 0.31

    def test_a_row_without_a_rationale_is_refused(self):
        """Varsayılan boş liste, bozuk bir gövdeyi sessiz bir tavsiyeye
        çevirirdi."""
        body = dict(self.BODY)
        body["rows"] = [{**self.BODY["rows"][0], "rationale": []}]
        with pytest.raises(ContractViolationError):
            portfolio_tools._normalize_rebalance(body)

    def test_a_row_missing_the_rationale_key_is_refused(self):
        body = dict(self.BODY)
        row = {key: value for key, value in self.BODY["rows"][0].items()
               if key != "rationale"}
        body["rows"] = [row]
        with pytest.raises(ContractViolationError):
            portfolio_tools._normalize_rebalance(body)

    def test_a_non_object_row_is_refused(self):
        body = dict(self.BODY)
        body["rows"] = ["THYAO"]
        with pytest.raises(ContractViolationError):
            portfolio_tools._normalize_rebalance(body)

    def test_the_raw_price_and_residual_never_reach_the_writer(self):
        """Satırın kendi cümlesi tutarı zaten içeriyor; yanına ham sayıyı
        koymak modeli ikisini birden basmaya davet ediyor."""
        row = portfolio_tools._normalize_rebalance(dict(self.BODY))["rows"][0]
        assert "price" not in row and "residual_base" not in row

    def test_a_non_dict_rationale_entry_is_dropped(self):
        body = dict(self.BODY)
        body["rows"] = [{**self.BODY["rows"][0],
                         "rationale": ["dize", self.BODY["rows"][0]["rationale"][0]]}]
        assert len(portfolio_tools._normalize_rebalance(body)["rows"][0]["rationale"]) == 1

    def test_the_gate_travels(self):
        body = dict(self.BODY)
        body["gate"] = {"open": False, "reason": "Önce uygunluk testini tamamlayın."}
        body["rows"] = []
        out = portfolio_tools._normalize_rebalance(body)
        assert out["gate"] == {"open": False,
                               "reason": "Önce uygunluk testini tamamlayın."}
        assert out["rows"] == []

    def test_a_missing_gate_is_refused(self):
        """Kapısı olmayan bir gövde, kapının hiç uygulanmadığı bir gövdeden
        ayırt edilemez."""
        body = {key: value for key, value in self.BODY.items() if key != "gate"}
        with pytest.raises(ContractViolationError):
            portfolio_tools._normalize_rebalance(body)

    def test_both_risk_axes_travel(self):
        out = portfolio_tools._normalize_rebalance(dict(self.BODY))
        assert out["measuredLevel"] == "Orta"
        assert out["declaredTolerance"] == "Yüksek"
        assert out["bindingBand"] == "Orta"

    def test_a_non_dict_unresolved_row_is_dropped(self):
        body = dict(self.BODY)
        body["unresolved"] = ["dize"]
        assert portfolio_tools._normalize_rebalance(body)["unresolved"] == []

    def test_no_target_is_carried_as_a_complete_answer(self):
        out = portfolio_tools._normalize_rebalance({
            "gate": {"open": True, "reason": "ok"},
            "disclaimer": "d", "summary": "", "hasTarget": False,
            "statement": "Hedef belirlemediniz.",
        })
        assert out["hasTarget"] is False
        assert "Hedef belirlemediniz." in out["statement"]

    def test_the_docstring_requires_a_reason_on_every_relayed_row(self):
        """Aracın var olma dayanağı bu cümle."""
        doc = " ".join(portfolio_tools.get_rebalance_plan.__doc__.split())
        assert "EVERY row you mention carries at least one of its `rationale` texts" in doc
        assert "A row without its reason is a recommendation" in doc

    def test_the_docstring_keeps_what_is_still_closed(self):
        doc = " ".join(portfolio_tools.get_rebalance_plan.__doc__.split())
        assert "Do NOT invent a row" in doc
        assert "Do NOT propose a target of your own" in doc
        assert "Do NOT tell the user to execute the list" in doc
        assert "Do NOT raise this subject unasked" in doc

    def test_the_docstring_forbids_re_ranking(self):
        """Sıra bir ÖLÇÜM: backend risk katkısına göre sıraladı."""
        doc = " ".join(portfolio_tools.get_rebalance_plan.__doc__.split())
        assert "The ORDER of `rows` is a measurement, not a preference" in doc
        assert "never re-rank" in doc

    def test_the_docstring_requires_the_disclaimer(self):
        doc = " ".join(portfolio_tools.get_rebalance_plan.__doc__.split())
        assert "Relay `disclaimer` whenever you relay any of this" in doc


class TestRegistration:
    async def test_register_attaches_the_tool(self):
        registered = []
        portfolio_tools.register(
            type("FakeMCP", (), {"tool": lambda self: registered.append})()
        )
        assert registered == [portfolio_tools.get_rebalance_plan]
