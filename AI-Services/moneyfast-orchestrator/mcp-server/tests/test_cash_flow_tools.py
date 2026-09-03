"""`get_cash_flow_summary` — sözleşme v2.16.

Bu araç yeni veri toplamıyor: `income_total` ve `spending_by_category`
backend'de zaten vardı ve arayüze veriliyordu. Eksik olan tek şey ajanın onu
görebilmesiydi -- ölçüldü, "ayda ne kadar yatırım yapabilirim" sorusu
EDUCATION_AGENT'a gidiyor, hiç araç çağrılmıyor ve cevap "Bu bilgi şu anda
mevcut değil." oluyordu.

Bu dosyanın koruduğu iki şey, ikisi de aynı aileden -- YOKLUĞU BİR TESPİTE
ÇEVİRMEMEK:

`has_data` -- 23 kullanıcının 3'ünde bankacılık hareketi var. Sıfır döndürmek
"hiç kazanmıyor ve hiç harcamıyor" demek olurdu.

`income_events` -- sıfır gelir iki farklı şey olabilir. Maaş aylık yattığı
için 30 günlük bir pencere hiç maaş içermeyebiliyor; ölçüldü, üç aylık maaş
geçmişi olan bir kullanıcıda tam olarak bu oldu.
"""

from __future__ import annotations

import pytest

import cash_flow_tools as cf
from backend_client import (
    ContractViolationError,
    InvalidInputError,
    UpstreamUnavailableError,
)

FULL = {
    "has_data": True, "coverage_note": None, "period_days": 90, "months_observed": 3.0,
    "currency_code": "TRY", "income_total": 112406.75, "income_events": 4,
    "expense_total": 67452.46, "net_total": 44954.29,
    "monthly_income": 37468.92, "monthly_expense": 22484.15,
    "monthly_net": 14984.76,
    "categories": [
        {"category": "Kira", "amount": 28000.0, "monthly_amount": 9333.33,
         "share_percent": 41.5},
        {"category": "Market", "amount": 10428.67, "monthly_amount": 3476.22,
         "share_percent": 15.5},
    ],
    "first_transaction_at": "2026-05-23T00:00:00Z",
    "last_transaction_at": "2026-08-26T00:00:00Z",
}

pytestmark = pytest.mark.asyncio

EMPTY = {
    "has_data": False, "coverage_note": None, "period_days": 90, "months_observed": 3.0,
    "currency_code": "TRY", "income_total": None, "income_events": 0,
    "expense_total": None, "net_total": None, "monthly_income": None,
    "monthly_expense": None, "monthly_net": None, "categories": [],
    "first_transaction_at": None, "last_transaction_at": None,
}


class TestRequest:
    async def test_it_reads_the_user_scoped_path(self, fake_backend):
        fake_backend.json("cash_flow", FULL)
        await cf.get_cash_flow_summary("u_123")
        assert fake_backend.last.method == "GET"
        assert "/banking/cash-flow/u_123" in str(fake_backend.last.url)

    async def test_no_window_sends_no_window(self, fake_backend):
        """Varsayılanı backend tutuyor. Burada bir sayı yazmak, iki yerde
        yaşayan ve ayrışabilen bir pencere demek olurdu."""
        fake_backend.json("cash_flow", FULL)
        await cf.get_cash_flow_summary("u_123")
        assert "days=" not in str(fake_backend.last.url)

    async def test_a_named_window_is_forwarded(self, fake_backend):
        fake_backend.json("cash_flow", FULL)
        await cf.get_cash_flow_summary("u_123", days=180)
        assert "days=180" in str(fake_backend.last.url)

    @pytest.mark.parametrize("days", [6, 0, -1, 366, 1000])
    async def test_a_window_outside_the_range_is_refused(self, fake_backend, days):
        with pytest.raises(InvalidInputError):
            await cf.get_cash_flow_summary("u_123", days=days)
        assert fake_backend.attempts == 0

    @pytest.mark.parametrize("days", [7, 90, 365])
    async def test_the_boundaries_are_inclusive(self, fake_backend, days):
        fake_backend.json("cash_flow", FULL)
        await cf.get_cash_flow_summary("u_123", days=days)
        assert f"days={days}" in str(fake_backend.last.url)


class TestCoverageNote:
    async def test_it_travels_when_present(self, fake_backend):
        fake_backend.json("cash_flow", {
            **FULL, "income_events": 2,
            "coverage_note": "Son 90 günde 2 gelir ödemesi görüldü.",
        })
        got = await cf.get_cash_flow_summary("u_123")
        assert got["coverage_note"] == "Son 90 günde 2 gelir ödemesi görüldü."

    async def test_a_full_window_carries_no_note(self, fake_backend):
        fake_backend.json("cash_flow", FULL)
        assert await cf.get_cash_flow_summary("u_123") is not None
        assert (await cf.get_cash_flow_summary("u_123"))["coverage_note"] is None


class TestPayload:
    async def test_every_contract_key_survives(self, fake_backend):
        fake_backend.json("cash_flow", FULL)
        got = await cf.get_cash_flow_summary("u_123")
        assert set(got) == set(cf._TOP_LEVEL) | {"categories"}

    async def test_the_figures_pass_through_unrounded(self, fake_backend):
        fake_backend.json("cash_flow", FULL)
        got = await cf.get_cash_flow_summary("u_123")
        assert got["monthly_net"] == 14984.76
        assert got["income_events"] == 4

    async def test_categories_keep_their_shape(self, fake_backend):
        fake_backend.json("cash_flow", FULL)
        got = await cf.get_cash_flow_summary("u_123")
        assert [row["category"] for row in got["categories"]] == ["Kira", "Market"]
        assert got["categories"][0]["share_percent"] == 41.5

    async def test_a_category_missing_a_derived_field_keeps_the_key(self, fake_backend):
        """Anahtarı düşürmek, `share_percent` okuyan bir tüketiciye KeyError
        verirdi; None ise "hesaplanamadı" diyor."""
        fake_backend.json("cash_flow", {
            **FULL, "categories": [{"category": "Kira", "amount": 1.0}],
        })
        got = await cf.get_cash_flow_summary("u_123")
        assert got["categories"][0]["share_percent"] is None
        assert got["categories"][0]["monthly_amount"] is None


class TestNoBankingRecords:
    async def test_it_is_an_answer_not_an_error(self, fake_backend):
        fake_backend.json("cash_flow", EMPTY)
        got = await cf.get_cash_flow_summary("u_123")
        assert got["has_data"] is False

    async def test_the_amounts_are_null_not_zero(self, fake_backend):
        """Kayıt yokluğu, sıfır gelir ve sıfır gider TESPİTİ değil."""
        fake_backend.json("cash_flow", EMPTY)
        got = await cf.get_cash_flow_summary("u_123")
        for field in ("income_total", "expense_total", "net_total", "monthly_net"):
            assert got[field] is None


class TestContractGuards:
    async def test_a_missing_flag_is_a_violation(self, fake_backend):
        fake_backend.json("cash_flow", {k: v for k, v in FULL.items()
                                            if k != "has_data"})
        with pytest.raises(ContractViolationError):
            await cf.get_cash_flow_summary("u_123")

    async def test_missing_categories_is_a_violation(self, fake_backend):
        fake_backend.json("cash_flow", {k: v for k, v in FULL.items()
                                            if k != "categories"})
        with pytest.raises(ContractViolationError):
            await cf.get_cash_flow_summary("u_123")

    async def test_a_non_object_category_is_a_violation(self, fake_backend):
        fake_backend.json("cash_flow", {**FULL, "categories": ["Kira"]})
        with pytest.raises(ContractViolationError):
            await cf.get_cash_flow_summary("u_123")

    async def test_a_category_without_an_amount_is_a_violation(self, fake_backend):
        fake_backend.json("cash_flow", {
            **FULL, "categories": [{"category": "Kira"}],
        })
        with pytest.raises(ContractViolationError):
            await cf.get_cash_flow_summary("u_123")

    async def test_an_unreachable_backend_raises(self, fake_backend):
        fake_backend.fail("cash_flow")
        with pytest.raises(UpstreamUnavailableError):
            await cf.get_cash_flow_summary("u_123")


def flat(text: str) -> str:
    """Satır sarmasını yok sayarak sözleşme metnini ara.

    Kural içerikte; nerede bölündüğü biçim meselesi."""
    return " ".join(text.split())


class TestContractWording:
    def test_zero_income_must_be_read_against_the_event_count(self):
        doc = flat(cf.get_cash_flow_summary.__doc__)
        assert "READ THIS BEFORE REPORTING A ZERO INCOME" in doc
        assert "false statement about someone's salary" in doc

    def test_the_leftover_is_not_a_recommendation(self):
        doc = flat(cf.get_cash_flow_summary.__doc__)
        assert "NOT a recommended investment amount" in doc

    def test_the_short_window_trap_is_recorded(self):
        assert "0 TRY income beside 6.697 TRY of spending" in \
            flat(cf.get_cash_flow_summary.__doc__)

    def test_the_coverage_sentence_is_relayed_not_reworded(self):
        """İki maaş 90 güne bölününce kişinin kazandığının üçte bir altına
        düşüyor. Kural önce prompt'a yazıldı ve model uygulamadı; bu yüzden
        cümle backend'de üretiliyor."""
        doc = flat(cf.get_cash_flow_summary.__doc__)
        assert "RELAY IT AS GIVEN" in doc
        assert "average to 41.333 TRY/month" in doc
        assert "the model did not follow it" in doc

    def test_no_records_is_a_complete_answer(self):
        assert "is a COMPLETE answer" in flat(cf.get_cash_flow_summary.__doc__)


class TestRegistration:
    def test_the_tool_is_attached(self):
        attached = []

        class FakeMCP:
            def tool(self):
                return lambda fn: attached.append(fn.__name__) or fn

        cf.register(FakeMCP())
        assert attached == ["get_cash_flow_summary"]
