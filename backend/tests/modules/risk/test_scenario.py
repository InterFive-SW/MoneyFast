"""Koşullu senaryo ve stres testi — ikisi de ÖLÇÜM, tahmin değil.

Bu dosyanın koruduğu üç şey:

1. **`r_squared` betanın zorunlu eşlikçisi.** Tek başına bir beta, ilişkinin ne
   kadar gerçek olduğu hakkında hiçbir şey söylemiyor. Canlı ölçüm: dolara
   karşı beta -0,68 ve r² 0,0011 -- yani faktör portföyün hareketinin binde
   birini açıklıyor. Cümle bunu söylemeseydi, veri desteklemezken "dolar %10
   çıksa portföyünüz %6,8 düşer" kesinliği kurulmuş olurdu.
2. **Cümle `GUA-003`'e takılmıyor.** Kural çekinceye bağlanmamış yön iddiasını
   engelliyor; buradaki cümle koşullu ("yükselseydi ... azalırdı") ve çekincesi
   aynı cümlede. Bir test bunu doğrudan uygunluk motoruna sorarak sabitliyor.
3. **Ölçülemeyen faktör reddediliyor.** En sık geleni faiz ve sistemde faiz
   SERİSİ yok. Bir döviz faktörünü vekil koymak, uydurulmuş bir sayıyı ölçüm
   diye vermek olurdu.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.modules.compliance import service as compliance_service
from app.modules.risk import scenario


def _series(days: int, step: float = 0.01, start: float = 100.0):
    """Sabit oranla büyüyen bir seri ve tarihleri."""
    base = date(2026, 1, 1)
    dates = [base + timedelta(days=index) for index in range(days)]
    values = [start * (1 + step) ** index for index in range(days)]
    return dates, values


def _bars(dates, values):
    """`candle_closes` biçimi: [(timestamp, close), ...]."""
    return list(zip(dates, values))


class TestSensitivity:
    def test_a_portfolio_that_tracks_the_factor_has_beta_one(self):
        dates, values = _series(50)
        measured = scenario.sensitivity(dates, values, _bars(dates, values))
        assert measured["beta"] == pytest.approx(1.0)
        assert measured["r_squared"] == pytest.approx(1.0)

    def test_a_portfolio_moving_twice_as_hard_has_beta_two(self):
        # Getiriler DEĞİŞMEK zorunda: sabit oranla büyüyen iki seride her
        # günlük getiri aynı sayı, faktörün varyansı sıfır ve eğim tanımsız.
        dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(40)]
        steps = [0.01, -0.02, 0.03, -0.01, 0.02, -0.03, 0.015, -0.005]
        factor, portfolio = [100.0], [100.0]
        for index in range(39):
            step = steps[index % len(steps)]
            factor.append(factor[-1] * (1 + step))
            portfolio.append(portfolio[-1] * (1 + 2 * step))
        measured = scenario.sensitivity(dates, portfolio, _bars(dates, factor))
        assert measured["beta"] == pytest.approx(2.0, rel=0.05)
        assert measured["r_squared"] == pytest.approx(1.0, abs=0.01)

    def test_too_few_shared_days_measure_nothing_rather_than_zero(self):
        """Sıfır beta "bu faktör portföyü hiç etkilemiyor" diye okunur ve bu,
        "ölçemedik"in tam tersi bir iddia."""
        dates, values = _series(2)
        assert scenario.sensitivity(dates, values, _bars(dates, values)) is None

    def test_a_factor_with_no_overlapping_days_measures_nothing(self):
        dates, values = _series(50)
        other = [day + timedelta(days=500) for day in dates]
        assert scenario.sensitivity(dates, values, _bars(other, values)) is None

    def test_a_flat_factor_cannot_produce_a_beta(self):
        """Sıfır varyanslı bir faktöre karşı eğim tanımsız."""
        dates, values = _series(50)
        flat = [100.0] * 50
        assert scenario.sensitivity(dates, values, _bars(dates, flat)) is None

    def test_a_short_window_is_measured_but_flagged_unreliable(self):
        dates, values = _series(20)
        measured = scenario.sensitivity(dates, values, _bars(dates, values))
        assert measured["is_statistically_reliable"] is False
        assert measured["observation_count"] == 19

    def test_a_long_window_is_reliable(self):
        dates, values = _series(120)
        measured = scenario.sensitivity(dates, values, _bars(dates, values))
        assert measured["is_statistically_reliable"] is True


class TestImpact:
    def test_the_impact_is_beta_times_the_shock(self):
        assert scenario.impact(0.7287, 10) == pytest.approx(7.287)

    def test_a_zero_shock_has_zero_impact(self):
        """Sorulmayan bir şok, hesaplanmış bir etki üretmemeli."""
        assert scenario.impact(0.7287, 0) == 0.0

    def test_a_negative_shock_flips_the_sign(self):
        assert scenario.impact(0.7287, -10) == pytest.approx(-7.287)


class TestNarrate:
    MEASURED = {"beta": 0.7287, "r_squared": 0.3621, "observation_count": 248,
                "is_statistically_reliable": True}

    def test_the_sentence_is_conditional_not_a_forecast(self):
        text = scenario.narrate("BIST 100", 10, self.MEASURED, "1Y")
        assert "yükselseydi" in text
        assert "artardı" in text

    def test_the_caveat_is_in_the_same_sentence(self):
        """İkiye bölüp ilk yarıyı göstermek, koşulu düşürüp iddiayı bırakmak
        olur."""
        text = scenario.narrate("BIST 100", 10, self.MEASURED, "1Y")
        assert text.endswith(f"{scenario.HEDGE_TR}.")

    def test_the_period_is_written_in_turkish_not_as_a_code(self):
        """"son 1Y", iç bir kodu kullanıcıya göstermek olurdu."""
        text = scenario.narrate("BIST 100", 10, self.MEASURED, "1Y")
        assert "son 1 yıl" in text
        assert "1Y" not in text

    def test_an_unknown_period_falls_back_to_what_was_given(self):
        text = scenario.narrate("BIST 100", 10, self.MEASURED, "2Y")
        assert "son 2Y" in text

    def test_a_downward_shock_reads_as_a_fall(self):
        text = scenario.narrate("BIST 100", -10, self.MEASURED, "1Y")
        assert "düşseydi" in text
        assert "azalırdı" in text

    def test_a_weak_relationship_is_stated_not_hidden(self):
        """Ölçülen gerçek durum: beta -0,68, r² 0,0011."""
        weak = {"beta": -0.6792, "r_squared": 0.0011, "observation_count": 222,
                "is_statistically_reliable": True}
        text = scenario.narrate("Dolar/TL", 10, weak, "1Y")
        assert "zayıf bir ilişkiye dayanıyor" in text
        assert "%0,1" in text

    def test_a_strong_relationship_says_nothing_extra(self):
        text = scenario.narrate("BIST 100", 10, self.MEASURED, "1Y")
        assert "zayıf" not in text

    def test_an_effect_that_rounds_to_zero_is_not_reported_as_zero(self):
        """"%0,0 artardı", ölçülmüş bir sıfır iddiası olur. Ölçümün söylediği,
        etkinin bu hassasiyette görünmediği."""
        tiny = {"beta": 0.004, "r_squared": 0.5, "observation_count": 200,
                "is_statistically_reliable": True}
        text = scenario.narrate("Ons altın", 10, tiny, "1Y")
        assert "ölçülebilir bir değişim göstermezdi" in text
        assert "%0,0" not in text

    def test_a_short_window_says_so(self):
        short = {"beta": 1.0, "r_squared": 0.9, "observation_count": 12,
                 "is_statistically_reliable": False}
        text = scenario.narrate("BIST 100", 10, short, "1M")
        assert "12 ortak güne dayanıyor" in text

    def test_a_missing_r_squared_does_not_break_the_sentence(self):
        blind = {"beta": 1.0, "observation_count": 200,
                 "is_statistically_reliable": True}
        assert scenario.narrate("BIST 100", 10, blind, "1Y").endswith(".")

    @pytest.mark.parametrize(
        "measured",
        [
            {"beta": 0.7287, "r_squared": 0.3621, "observation_count": 248,
             "is_statistically_reliable": True},
            {"beta": -0.6792, "r_squared": 0.0011, "observation_count": 222,
             "is_statistically_reliable": True},
            {"beta": 0.004, "r_squared": 0.0, "observation_count": 194,
             "is_statistically_reliable": True},
            {"beta": 1.0, "r_squared": 0.9, "observation_count": 12,
             "is_statistically_reliable": False},
        ],
    )
    def test_every_shape_of_sentence_passes_the_compliance_gate(self, measured):
        """Asıl kapı. `GUA-003` çekinceye bağlanmamış yön iddiasını engelliyor
        ve bu cümlelerin hiçbiri bir yön iddiası değil -- faktörün ne yapacağı
        hakkında hiçbir şey söylemiyorlar. Uygunluk motoru kessseydi, kullanıcı
        cevabı hiç görmezdi."""
        for shock in (10, -10):
            text = scenario.narrate("Dolar/TL", shock, measured, "1Y")
            result = compliance_service.validate(
                {"user_query": "dolar yükselirse ne olur", "draft_response": text}
            )
            assert result["violations"] == [], text


class TestWorstDays:
    def test_the_worst_days_come_back_worst_first(self):
        dates = [date(2026, 1, day) for day in range(1, 7)]
        values = [100, 90, 95, 80, 82, 81]
        rows = scenario.worst_days(dates, values, count=3)
        assert [round(row["return_pct"], 1) for row in rows] == [-15.8, -10.0, -1.2]

    def test_each_day_is_the_day_the_move_landed_on(self):
        """`simple_returns` n-1 değer üretiyor; i'inci getiri dates[i+1]'e ait.
        Bir gün kaydırmak, düşüşü olmadığı güne yazmak olurdu."""
        dates = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)]
        rows = scenario.worst_days(dates, [100, 50, 55])
        assert rows[0]["date"] == date(2026, 1, 2)

    def test_a_series_too_short_for_a_return_yields_nothing(self):
        assert scenario.worst_days([date(2026, 1, 1)], [100]) == []

    def test_fewer_days_than_asked_for_returns_what_exists(self):
        dates = [date(2026, 1, 1), date(2026, 1, 2)]
        assert len(scenario.worst_days(dates, [100, 90], count=5)) == 1


class TestFactorReplay:
    def test_it_finds_the_window_where_the_factor_moved_hardest(self):
        dates = [date(2026, 1, day) for day in range(1, 12)]
        values = [100.0] * 11
        factor = [100, 101, 102, 103, 104, 105, 130, 131, 132, 133, 134]
        replay = scenario.factor_replay(dates, values, _bars(dates, factor), window=3)
        assert replay["factor_move_pct"] == pytest.approx(26.2, abs=0.5)
        assert replay["start_date"] == date(2026, 1, 4)

    def test_a_sharp_fall_counts_as_hard_as_a_sharp_rise(self):
        """En sert hareket yönsüzdür; yalnızca yükselişe bakmak, çöküşü
        gözden kaçırırdı."""
        dates = [date(2026, 1, day) for day in range(1, 8)]
        factor = [100, 100, 100, 100, 60, 60, 60]
        replay = scenario.factor_replay(dates, values=[100.0] * 7,
                                        factor_bars=_bars(dates, factor), window=2)
        assert replay["factor_move_pct"] < -30

    def test_the_portfolio_move_covers_exactly_the_same_days(self):
        dates = [date(2026, 1, day) for day in range(1, 8)]
        values = [100, 100, 100, 100, 110, 110, 110]
        factor = [100, 100, 100, 100, 150, 150, 150]
        replay = scenario.factor_replay(dates, values, _bars(dates, factor), window=2)
        assert replay["portfolio_move_pct"] == pytest.approx(10.0)
        assert replay["trading_days"] == 2

    def test_too_little_shared_history_measures_nothing(self):
        """Ölçülemeyen faktör listede yer almaz; sıfırla görünmek "o faktör
        portföyü hiç etkilemedi" demek olurdu."""
        dates = [date(2026, 1, 1), date(2026, 1, 2)]
        assert scenario.factor_replay(dates, [100, 101],
                                      _bars(dates, [10, 11]), window=5) is None

    def test_a_factor_trading_on_other_days_measures_nothing(self):
        dates = [date(2026, 1, day) for day in range(1, 12)]
        other = [day + timedelta(days=500) for day in dates]
        assert scenario.factor_replay(dates, [100.0] * 11,
                                      _bars(other, [100.0] * 11), window=3) is None

    def test_a_perfectly_flat_factor_reports_no_episode(self):
        """Hiç oynamamış bir faktörün "en sert hareketi" yoktur."""
        dates = [date(2026, 1, day) for day in range(1, 12)]
        assert scenario.factor_replay(dates, [100.0] * 11,
                                      _bars(dates, [100.0] * 11), window=3) is None


class TestFactorSet:
    def test_interest_rates_are_deliberately_absent(self):
        """Sistemde faiz SERİSİ yok (`TR_POLICY_RATE` bir sabit). Buraya bir
        ad yazmak onu ölçülebilir yapmaz."""
        assert "TR_POLICY_RATE" not in scenario.FACTORS
        assert not any("RATE" in key or "FAIZ" in key for key in scenario.FACTORS)

    def test_every_factor_has_a_turkish_name_to_show(self):
        """Sembol kullanıcıya sızmaz; `prompts.py`'deki NAMING kuralıyla aynı."""
        for symbol, label in scenario.FACTORS.items():
            assert label and label != symbol
