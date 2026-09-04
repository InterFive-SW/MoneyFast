"""Teknik göstergeler ve onların Türkçe okuması."""

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.market import technicals


def bars(closes, volumes=None):
    """Kapanış listesinden bar sözlükleri.

    Zaman damgası GERÇEK bir `datetime`: `market_service.candle_series` onu
    böyle veriyor ve `max_drawdown` damgadan `.date()` istiyor. Metin
    kullanmak, testin üretimde olmayan bir girdiyi ölçmesi olurdu.
    """
    return [
        {
            "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": None if volumes is None else volumes[i],
        }
        for i, close in enumerate(closes)
    ]


class TestSma:
    def test_it_averages_the_last_n(self):
        assert technicals.sma([1, 2, 3, 4, 5], 5) == 3.0
        assert technicals.sma([1, 2, 3, 4, 5], 2) == 4.5

    def test_too_few_values_is_none_not_a_partial_average(self):
        """60 barlık bir seriden "200 günlük ortalama" üretmek, adı 200 olan
        bir sayıyla 60 günü ölçmektir."""
        assert technicals.sma([1, 2, 3], 5) is None

    def test_a_zero_window_has_no_answer(self):
        assert technicals.sma([1, 2, 3], 0) is None


class TestRsi:
    def test_a_series_that_only_rises_pins_the_indicator_at_the_top(self):
        assert technicals.rsi(list(range(1, 40))) == 100.0

    def test_a_flat_series_has_no_relative_strength(self):
        """Ne kazanç ne kayıp: RS tanımsız, gösterge ortada."""
        assert technicals.rsi([10.0] * 30) == 50.0

    def test_it_needs_one_more_close_than_its_period(self):
        assert technicals.rsi([1, 2, 3], period=14) is None
        assert technicals.rsi(list(range(15)), period=14) is not None

    def test_a_mixed_series_lands_between_the_bounds(self):
        closes = [44, 44.3, 44.1, 44.6, 43.4, 44.3, 44.8, 45.1, 45.4,
                  45.4, 46.2, 46.3, 46.3, 46, 46.0, 46.0, 44.3, 44.1]
        value = technicals.rsi(closes)
        assert 0 < value < 100


class TestTrendClassification:
    def test_above_both_averages_is_an_uptrend(self):
        assert technicals.classify(110.0, 100.0, 100.0) == "UPTREND"

    def test_below_both_is_a_downtrend(self):
        assert technicals.classify(90.0, 100.0, 100.0) == "DOWNTREND"

    def test_the_two_averages_disagreeing_is_no_direction(self):
        """Tek bir ortalamaya bakıp yön ilan etmek, ölçümün söylemediğini
        söylemek olurdu."""
        assert technicals.classify(105.0, 100.0, 110.0) == "SIDEWAYS"

    def test_a_hair_above_is_not_a_trend(self):
        """Eşiksiz bir karşılaştırma her gün başka bir eğilim ilan ederdi."""
        assert technicals.classify(100.5, 100.0, 100.0) == "SIDEWAYS"

    def test_a_missing_average_means_unknown_not_sideways(self):
        assert technicals.classify(100.0, None, 100.0) == "UNKNOWN"
        assert technicals.classify(100.0, 100.0, None) == "UNKNOWN"

    def test_a_zero_average_cannot_be_compared_against(self):
        assert technicals.classify(100.0, 0.0, 100.0) == "UNKNOWN"


class TestCompute:
    def test_no_bars_yields_every_field_empty(self):
        out = technicals.compute([])
        assert out["observations"] == 0
        assert out["trend"] == "UNKNOWN"
        assert out["last_close"] is None
        assert out["rsi_14"] is None

    def test_a_short_history_fills_what_it_can_and_leaves_the_rest_none(self):
        out = technicals.compute(bars([100.0 + i for i in range(30)]))
        assert out["sma_20"] is not None
        assert out["sma_50"] is None
        assert out["sma_200"] is None
        assert out["pct_from_sma_50"] is None

    def test_a_rising_series_reads_as_an_uptrend(self):
        out = technicals.compute(bars([100.0 + i for i in range(260)]))
        assert out["trend"] == "UPTREND"
        assert out["up_days_recent"] == 20
        assert out["recent_window"] == 20
        assert out["pct_from_sma_50"] > 0

    def test_the_52_week_position_is_measured_against_the_year(self):
        out = technicals.compute(bars([100.0 + i for i in range(260)]))
        # Son bar serinin en yükseği: aralığın tepesinde.
        assert out["week52_position_pct"] == pytest.approx(100.0)

    def test_a_flat_year_has_no_range_to_place_the_price_in(self):
        """High ile low eşitse "aralığın %50'sinde" demek, olmayan bir
        aralığın ortasını işaret etmektir."""
        out = technicals.compute(bars([100.0] * 260))
        assert out["week52_position_pct"] is None

    def test_a_series_that_actually_falls_reports_its_drawdown(self):
        """Yalnızca yükselen serilerle ölçmek, en büyük düşüşü hiç
        hesaplatmıyordu: `max_drawdown` düşüş yoksa None döner."""
        closes = [100.0 + i for i in range(60)] + [159.0 - 2 * i for i in range(40)]
        out = technicals.compute(bars(closes))

        assert out["max_drawdown_pct"] is not None
        assert out["max_drawdown_pct"] < 0
        assert out["annualised_volatility"] is not None

    def test_a_series_that_only_rises_has_no_drawdown_to_report(self):
        """Hiç düşmemiş bir seride "en büyük düşüş: %0" demek, olmayan bir
        ölçümü sıfır diye raporlamaktır."""
        out = technicals.compute(bars([100.0 + i for i in range(60)]))
        assert out["max_drawdown_pct"] is None

    def test_a_single_bar_has_no_up_day_count(self):
        out = technicals.compute(bars([100.0]))
        assert out["up_days_recent"] is None
        assert out["recent_window"] is None


class TestVolumeRatio:
    def test_the_last_session_is_compared_against_the_ones_before_it(self):
        volumes = [100] * 20 + [300]
        out = technicals.compute(bars([100.0 + i for i in range(21)], volumes))
        # Son bar ortalamanın DIŞINDA: 300 / 100.
        assert out["volume_vs_average"] == pytest.approx(3.0)

    def test_missing_volume_is_not_guessed(self):
        out = technicals.compute(bars([100.0 + i for i in range(21)]))
        assert out["volume_vs_average"] is None

    def test_too_short_a_history_has_no_average_to_compare_against(self):
        out = technicals.compute(bars([100.0, 101.0], [10, 20]))
        assert out["volume_vs_average"] is None

    def test_an_all_zero_window_cannot_be_divided_by(self):
        volumes = [0] * 20 + [5]
        out = technicals.compute(bars([100.0 + i for i in range(21)], volumes))
        assert out["volume_vs_average"] is None

    def test_a_gap_in_the_window_is_not_averaged_over(self):
        """Eksik bir seansı yok sayıp kalanların ortalamasını almak, hacmi
        olduğundan farklı gösterir."""
        volumes = [100] * 10 + [None] + [100] * 9 + [300]
        out = technicals.compute(bars([100.0 + i for i in range(21)], volumes))
        assert out["volume_vs_average"] is None


class TestNarrate:
    def test_it_names_what_was_measured_and_the_trend(self):
        text = technicals.narrate("AKBNK", {
            "trend": "UPTREND", "last_close": 100.0,
            "pct_from_sma_50": 8.2, "up_days_recent": 14,
            "recent_window": 20, "week52_position_pct": 72.5,
        })
        assert "AKBNK" in text
        assert "50 günlük ortalamasının %8,2 üzerinde" in text
        assert "yükseliş eğiliminde" in text

    def test_the_forward_reading_is_conditional_and_carries_its_caveat(self):
        """İzin verilen şey koşullu okuma. Çekince ayrılamaz: cümleyi ikiye
        bölüp ilk yarısını göstermek, koşulu düşürüp iddiayı bırakmaktır."""
        text = technicals.narrate("AKBNK", {
            "trend": "UPTREND", "last_close": 100.0, "pct_from_sma_50": 8.2,
        })
        assert "sürdüğü sürece" in text
        assert technicals.HEDGE_TR in text

    def test_a_sideways_reading_makes_no_forward_claim_at_all(self):
        text = technicals.narrate("XU100", {
            "trend": "SIDEWAYS", "last_close": 100.0, "pct_from_sma_50": 0.2,
        })
        assert "yatay seyrediyor" in text
        assert "beklenebilir" not in text

    def test_an_unmeasurable_trend_produces_no_sentence(self):
        """Boş bir cümle üretmektense hiç üretmemek."""
        assert technicals.narrate("X", {"trend": "UNKNOWN", "last_close": 1.0}) is None
        assert technicals.narrate("X", {"trend": "UPTREND", "last_close": None}) is None

    def test_no_facts_means_no_sentence(self):
        assert technicals.narrate("X", {"trend": "UPTREND", "last_close": 10.0}) is None

    def test_it_falls_back_to_the_20_day_average_when_the_50_is_missing(self):
        text = technicals.narrate("X", {
            "trend": "UPTREND", "last_close": 10.0, "pct_from_sma_20": 4.0,
        })
        assert "20 günlük ortalamasının %4,0 üzerinde" in text

    def test_below_the_average_is_worded_as_below(self):
        text = technicals.narrate("X", {
            "trend": "DOWNTREND", "last_close": 10.0, "pct_from_sma_50": -6.5,
        })
        assert "%6,5 altında" in text
        assert "düşüş eğiliminde" in text

    def test_numbers_are_written_the_turkish_way(self):
        text = technicals.narrate("X", {
            "trend": "UPTREND", "last_close": 10.0, "pct_from_sma_50": 1234.5,
        })
        assert "1.234,5" in text


class TestLocativeSuffix:
    def test_the_suffix_follows_how_the_number_is_SAID(self):
        """14 "dört" ile bittiği için "14'ünde"dir, "14'inde" değil."""
        assert technicals._locative(14) == "14'ünde"
        assert technicals._locative(3) == "3'ünde"
        assert technicals._locative(6) == "6'sında"
        assert technicals._locative(9) == "9'unda"
        assert technicals._locative(20) == "20'sinde"

    def test_a_number_outside_the_table_goes_bare_rather_than_wrong(self):
        assert technicals._locative(37) == "37"
