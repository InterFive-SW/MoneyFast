"""\"Ne olur?\" simülasyonunun saf kısmı.

Yeni bir matematik yok: `calculate` zaten dışarıdan bir pozisyon listesi
alıyor, simülasyonun tek yaptığı ikinci bir liste üretmek. Bu testler o
listenin dürüst üretildiğini koruyor.
"""

from __future__ import annotations

from app.modules.risk import service


def position(symbol, quantity, value, sector="Industrials", asset="stock", currency="TRY"):
    return {
        "symbol": symbol, "quantity": quantity, "market_value": value,
        "sector": sector, "asset_class": asset, "instrument_currency": currency,
    }


HELD = [position("THYAO", 10, 3000.0), position("ASELS", 5, 2000.0)]


class TestApplyChanges:
    def test_adding_to_a_held_position_scales_its_value(self):
        out = service.apply_changes(HELD, [
            {"symbol": "THYAO", "quantity_delta": 10, "unit_value": 300.0},
        ])
        thyao = next(p for p in out if p["symbol"] == "THYAO")
        assert thyao["quantity"] == 20
        assert thyao["market_value"] == 6000.0

    def test_reducing_a_position_scales_it_down(self):
        out = service.apply_changes(HELD, [
            {"symbol": "THYAO", "quantity_delta": -5, "unit_value": 300.0},
        ])
        thyao = next(p for p in out if p["symbol"] == "THYAO")
        assert thyao["quantity"] == 5
        assert thyao["market_value"] == 1500.0

    def test_selling_everything_removes_the_row(self):
        """Sıfır değerli bir satır `effective_n` içinde hâlâ bir isim sayılır;
        bırakmak, kullanıcının artık sahip olmadığı bir dağılımı raporlar."""
        out = service.apply_changes(HELD, [
            {"symbol": "THYAO", "quantity_delta": -10, "unit_value": 300.0},
        ])
        assert [p["symbol"] for p in out] == ["ASELS"]

    def test_selling_more_than_held_closes_at_zero(self):
        """Kimse elindekinden fazlasını satamaz; negatif ağırlık, yoğunlaşma
        hesabına var olmayan bir pay verirdi."""
        out = service.apply_changes(HELD, [
            {"symbol": "THYAO", "quantity_delta": -999, "unit_value": 300.0},
        ])
        assert [p["symbol"] for p in out] == ["ASELS"]

    def test_a_new_symbol_is_added_with_its_own_attributes(self):
        out = service.apply_changes(HELD, [
            {"symbol": "NVDA", "quantity_delta": 2, "unit_value": 5000.0,
             "asset_class": "stock", "sector": "Technology", "instrument_currency": "USD"},
        ])
        nvda = next(p for p in out if p["symbol"] == "NVDA")
        assert nvda["market_value"] == 10000.0
        assert nvda["sector"] == "Technology"
        assert nvda["instrument_currency"] == "USD"

    def test_a_new_symbol_falls_back_when_attributes_are_missing(self):
        out = service.apply_changes(HELD, [
            {"symbol": "NVDA", "quantity_delta": 1, "unit_value": 100.0},
        ])
        nvda = next(p for p in out if p["symbol"] == "NVDA")
        assert nvda["asset_class"] == "EQUITY"
        assert nvda["sector"] == "UNCLASSIFIED"
        assert nvda["instrument_currency"] == "TRY"

    def test_selling_something_not_held_is_ignored_not_shorted(self):
        """Tutulmayan bir şeyi satmak bir portföy değil, bir yazım hatası."""
        out = service.apply_changes(HELD, [
            {"symbol": "GARAN", "quantity_delta": -5, "unit_value": 100.0},
        ])
        assert {p["symbol"] for p in out} == {"THYAO", "ASELS"}

    def test_a_zero_delta_changes_nothing(self):
        out = service.apply_changes(HELD, [
            {"symbol": "THYAO", "quantity_delta": 0, "unit_value": 300.0},
        ])
        assert out == HELD or {p["symbol"]: p["market_value"] for p in out} == {
            "THYAO": 3000.0, "ASELS": 2000.0
        }

    def test_the_original_positions_are_not_mutated(self):
        """Karşılaştırmanın "önce" tarafı, "sonra" hesaplanırken bozulmamalı."""
        service.apply_changes(HELD, [
            {"symbol": "THYAO", "quantity_delta": 50, "unit_value": 300.0},
        ])
        assert HELD[0]["quantity"] == 10
        assert HELD[0]["market_value"] == 3000.0

    def test_several_changes_apply_together(self):
        out = service.apply_changes(HELD, [
            {"symbol": "THYAO", "quantity_delta": -10, "unit_value": 300.0},
            {"symbol": "NVDA", "quantity_delta": 1, "unit_value": 1000.0},
        ])
        assert {p["symbol"] for p in out} == {"ASELS", "NVDA"}

    def test_no_changes_returns_the_same_portfolio(self):
        out = service.apply_changes(HELD, [])
        assert {p["symbol"] for p in out} == {"THYAO", "ASELS"}


class TestSummaryAndDeltas:
    def test_the_summary_picks_the_comparable_figures(self):
        metrics = {
            "volatility_annualized": 0.18,
            "max_drawdown": {"value": -0.11},
            "concentration": {"hhi": 0.3, "effective_n": 3.3},
        }
        side = service.summarise_for_simulation(metrics, {"score": 80.0, "level": "Düşük"})
        assert side == {
            "score": 80.0, "level": "Düşük", "volatility": 0.18,
            "hhi": 0.3, "effective_n": 3.3, "max_drawdown": -0.11,
        }

    def test_missing_blocks_yield_none_rather_than_zero(self):
        side = service.summarise_for_simulation({}, {})
        assert side["volatility"] is None
        assert side["hhi"] is None
        assert side["max_drawdown"] is None

    def test_deltas_are_after_minus_before(self):
        before = {"score": 80.0, "volatility": 0.18, "hhi": 0.30, "effective_n": 3.3,
                  "max_drawdown": -0.11}
        after = {"score": 72.0, "volatility": 0.24, "hhi": 0.45, "effective_n": 2.2,
                 "max_drawdown": -0.15}
        deltas = service.simulation_deltas(before, after)
        assert deltas["score"] == -8.0
        assert round(deltas["volatility"], 4) == 0.06
        assert deltas["effective_n"] == -1.1

    def test_an_unmeasurable_side_yields_none_not_zero(self):
        """Sıfır "değişmedi" diye okunur; bu, "ölçemedik"ten farklı bir iddia."""
        deltas = service.simulation_deltas({"score": 80.0}, {"score": None})
        assert deltas["score"] is None
        deltas = service.simulation_deltas({"score": None}, {"score": 80.0})
        assert deltas["score"] is None

    def test_an_unchanged_metric_reports_a_real_zero(self):
        deltas = service.simulation_deltas({"hhi": 0.3}, {"hhi": 0.3})
        assert deltas["hhi"] == 0.0
