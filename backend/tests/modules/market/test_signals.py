"""Yön sinyali motoru.

En önemli test `TestWording`: motorun üretebileceği HER cümle, uygunluk
kural paketinin regex'lerine karşı taranıyor. Cümlenin kurallardan geçmesi
tesadüf olmamalı ve buradan başka hiçbir yer bunu garanti etmiyor -- uygunluk
kapısı yalnızca sohbet taslağına uygulanıyor, bu modülün beslediği REST uçları
oradan geçmiyor.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.market import signals, technicals


def _bars(closes, start_day=1):
    """Elle doğrulanabilir bar dizisi."""
    return [
        {
            "timestamp": date(2026, 1, 1),
            "open": close, "high": close, "low": close,
            "close": close, "volume": 1000,
        }
        for close in closes
    ]


def _rising(n=260):
    return _bars([100.0 + i for i in range(n)])


def _falling(n=260):
    return _bars([500.0 - i for i in range(n)])


class TestTechnicalEvidence:
    def test_an_unmeasured_indicator_produces_no_evidence(self):
        """Ölçülemeyen gösterge kanıt üretmez, sıfır saymaz -- `technicals`in
        `None` döndürme kuralının bu katmandaki karşılığı."""
        rows = signals.technical_evidence(technicals.compute([]))
        assert rows == []

    def test_a_rising_series_leans_up(self):
        rows = signals.technical_evidence(technicals.compute(_rising()))
        keys = {row["key"] for row in rows}
        assert "sma_50_vs_200" in keys
        assert any(row["direction"] == signals.UP for row in rows)

    def test_a_falling_series_leans_down(self):
        rows = signals.technical_evidence(technicals.compute(_falling()))
        assert any(row["direction"] == signals.DOWN for row in rows)

    def test_a_flat_gap_is_neutral_not_a_direction(self):
        """Binde birlik bir fark yön değil gürültü; eşiksiz bir karşılaştırma
        her gün başka bir eğilim ilan ederdi."""
        rows = signals.technical_evidence({
            "sma_50": 100.0, "sma_200": 100.2, "trend": "SIDEWAYS",
        })
        gap = next(r for r in rows if r["key"] == "sma_50_vs_200")
        assert gap["direction"] == signals.NEUTRAL

    def test_rsi_is_reported_but_casts_no_vote(self):
        """70 üstü "düşecek" demek değil: gösterge momentumu ölçüyor ve yüksek
        momentum hem devam hem dönüş sayılabiliyor."""
        rows = signals.technical_evidence({"rsi_14": 82.0})
        assert rows[0]["key"] == "rsi_14"
        assert rows[0]["direction"] == signals.NEUTRAL

    def test_the_range_position_is_described_as_a_position(self):
        """`MARKET_DATA_AGENT`'ın "never call a price cheap or expensive"
        kuralı cümlenin kendisinde de geçerli."""
        rows = signals.technical_evidence({"week52_position_pct": 92.0})
        text = rows[0]["text"]
        assert "seviyesinde" in text
        for banned in ("ucuz", "pahalı", "cazip"):
            assert banned not in text.lower()

    @pytest.mark.parametrize("position,expected", [
        (95.0, signals.UP), (50.0, signals.NEUTRAL), (5.0, signals.DOWN),
    ])
    def test_range_position_bands(self, position, expected):
        rows = signals.technical_evidence({"week52_position_pct": position})
        assert rows[0]["direction"] == expected

    @pytest.mark.parametrize("up_days,expected", [
        (16, signals.UP), (10, signals.NEUTRAL), (4, signals.DOWN),
    ])
    def test_up_day_bands(self, up_days, expected):
        rows = signals.technical_evidence(
            {"up_days_recent": up_days, "recent_window": 20}
        )
        assert rows[0]["direction"] == expected

    def test_a_zero_window_is_not_divided_by(self):
        assert signals.technical_evidence(
            {"up_days_recent": 3, "recent_window": 0}
        ) == []

    def test_a_zero_long_average_is_not_divided_by(self):
        assert signals.technical_evidence({"sma_50": 10.0, "sma_200": 0.0}) == []

    def test_the_price_distance_falls_back_to_the_shorter_average(self):
        """200 günlük yoksa 50 okunur; ikisi birden okunmaz, çünkü aynı şeyin
        iki görünümü tek kanıt sayılmalı."""
        rows = signals.technical_evidence(
            {"pct_from_sma_50": 6.0, "pct_from_sma_200": None}
        )
        assert [row["key"] for row in rows] == ["price_vs_sma_50"]

    def test_an_unknown_trend_is_not_evidence(self):
        assert signals.technical_evidence({"trend": "UNKNOWN"}) == []

    def test_a_flat_price_distance_is_neutral(self):
        rows = signals.technical_evidence({"pct_from_sma_200": 0.4})
        assert rows[0]["direction"] == signals.NEUTRAL

    def test_a_price_below_the_average_leans_down(self):
        rows = signals.technical_evidence({"pct_from_sma_200": -7.0})
        assert rows[0]["direction"] == signals.DOWN
        assert "altında" in rows[0]["text"]


class TestFundamentalEvidence:
    def test_nothing_measured_produces_nothing(self):
        assert signals.fundamental_evidence(None, None) == []

    def test_a_snapshot_never_produces_a_change_claim(self):
        """Anlık görüntü bir SEVİYEDİR, değişim değil. "arttı/düştü" yalnızca
        çeyreklik seriden gelir."""
        rows = signals.fundamental_evidence({"profit_margin": 0.2}, None)
        for row in rows:
            assert "arttı" not in row["text"]
            assert "azaldı" not in row["text"]

    @pytest.mark.parametrize("roe,expected", [
        (0.30, signals.UP), (0.05, signals.NEUTRAL), (-0.10, signals.DOWN),
    ])
    def test_return_on_equity_bands(self, roe, expected):
        rows = signals.fundamental_evidence({"return_on_equity": roe}, None)
        assert rows[0]["direction"] == expected

    def test_heavy_debt_leans_down_and_never_up(self):
        """Borç oranı ters okunuyor: yüksek borç yön olarak aşağı, düşük borç
        yukarı DEĞİL -- borcun olmaması bir üstünlük iddiası değil."""
        heavy = signals.fundamental_evidence({"debt_to_equity": 400.0}, None)
        light = signals.fundamental_evidence({"debt_to_equity": 10.0}, None)
        assert heavy[0]["direction"] == signals.DOWN
        assert light[0]["direction"] == signals.NEUTRAL

    def test_quarterly_change_needs_adjacent_periods(self):
        """Sağlayıcı çeyrek atlıyor; iki atlanmış çeyreği yan yana koyup "bir
        önceki çeyreğe göre" demek yanlış olurdu."""
        quarterly = {
            "previous_is_adjacent": False,
            "periods": [
                {"period_end": date(2026, 6, 30), "label": "2026Q2", "net_income": 120},
                {"period_end": date(2025, 12, 31), "label": "2025Q4", "net_income": 100},
            ],
        }
        rows = signals.fundamental_evidence(None, quarterly)
        assert rows == []

    def test_an_adjacent_quarter_produces_a_change(self):
        quarterly = {
            "previous_is_adjacent": True,
            "periods": [
                {"period_end": date(2026, 6, 30), "label": "2026Q2", "net_income": 120},
                {"period_end": date(2026, 3, 31), "label": "2026Q1", "net_income": 100},
            ],
        }
        rows = signals.fundamental_evidence(None, quarterly)
        assert rows[0]["key"] == "quarterly_net_income_qoq"
        assert rows[0]["direction"] == signals.UP
        assert "%20,0 arttı" in rows[0]["text"]

    def test_a_shrinking_quarter_leans_down(self):
        quarterly = {
            "previous_is_adjacent": True,
            "periods": [
                {"period_end": date(2026, 6, 30), "label": "2026Q2", "net_income": 80},
                {"period_end": date(2026, 3, 31), "label": "2026Q1", "net_income": 100},
            ],
        }
        rows = signals.fundamental_evidence(None, quarterly)
        assert rows[0]["direction"] == signals.DOWN
        assert "azaldı" in rows[0]["text"]

    def test_an_unchanged_quarter_is_neutral(self):
        quarterly = {
            "previous_is_adjacent": True,
            "periods": [
                {"period_end": date(2026, 6, 30), "label": "2026Q2", "net_income": 100},
                {"period_end": date(2026, 3, 31), "label": "2026Q1", "net_income": 100},
            ],
        }
        assert signals.fundamental_evidence(None, quarterly)[0]["direction"] == (
            signals.NEUTRAL
        )

    def test_a_zero_base_is_not_divided_by(self):
        quarterly = {
            "previous_is_adjacent": True,
            "periods": [
                {"period_end": date(2026, 6, 30), "label": "2026Q2", "net_income": 50},
                {"period_end": date(2026, 3, 31), "label": "2026Q1", "net_income": 0},
            ],
        }
        assert signals.fundamental_evidence(None, quarterly) == []

    def test_the_year_ago_quarter_is_found_by_index_not_position(self):
        """`periods[4]` demek, sağlayıcının hiç çeyrek atlamadığını varsaymak
        olurdu. Atlıyor -- ve yanlış satırı "geçen yılın aynı çeyreği" diye
        okumak büyüme oranını sessizce yanlış yapardı."""
        quarterly = {
            "year_ago_available": True,
            "periods": [
                {"period_end": date(2026, 6, 30), "label": "2026Q2", "total_revenue": 200},
                {"period_end": date(2026, 3, 31), "total_revenue": 190},
                {"period_end": date(2025, 9, 30), "total_revenue": 180},  # 2025Q4 atlanmış
                {"period_end": date(2025, 6, 30), "total_revenue": 100},  # aranan
            ],
        }
        rows = signals.fundamental_evidence(None, quarterly)
        revenue = next(r for r in rows if r["key"] == "quarterly_revenue_yoy")
        assert "%100,0 arttı" in revenue["text"]

    def test_a_missing_year_ago_quarter_produces_nothing(self):
        quarterly = {
            "year_ago_available": True,
            "periods": [
                {"period_end": date(2026, 6, 30), "total_revenue": 200},
                {"period_end": date(2026, 3, 31), "total_revenue": 190},
            ],
        }
        assert [r for r in signals.fundamental_evidence(None, quarterly)
                if r["key"] == "quarterly_revenue_yoy"] == []

    def test_a_period_without_a_date_is_skipped(self):
        quarterly = {"year_ago_available": True, "periods": [{"total_revenue": 1}]}
        assert signals.fundamental_evidence(None, quarterly) == []

    def test_no_periods_at_all(self):
        assert signals.fundamental_evidence(None, {"periods": []}) == []

    def test_a_latest_period_without_a_date_stops_the_year_ago_lookup(self):
        """`_quarter_index` tarihsiz satırda `None` döner; onu sayı gibi
        kullanmak sessiz bir hata olurdu."""
        quarterly = {
            "year_ago_available": True,
            "periods": [{"total_revenue": 200}, {"period_end": date(2025, 6, 30)}],
        }
        assert signals.fundamental_evidence(None, quarterly) == []

    def test_a_shrinking_year_leans_down(self):
        quarterly = {
            "year_ago_available": True,
            "periods": [
                {"period_end": date(2026, 6, 30), "total_revenue": 50},
                {"period_end": date(2025, 6, 30), "total_revenue": 100},
            ],
        }
        rows = signals.fundamental_evidence(None, quarterly)
        assert rows[0]["direction"] == signals.DOWN
        assert "azaldı" in rows[0]["text"]

    def test_an_unchanged_year_is_neutral(self):
        quarterly = {
            "year_ago_available": True,
            "periods": [
                {"period_end": date(2026, 6, 30), "total_revenue": 100},
                {"period_end": date(2025, 6, 30), "total_revenue": 100},
            ],
        }
        assert signals.fundamental_evidence(None, quarterly)[0]["direction"] == (
            signals.NEUTRAL
        )

    def test_a_zero_year_ago_base_is_not_divided_by(self):
        quarterly = {
            "year_ago_available": True,
            "periods": [
                {"period_end": date(2026, 6, 30), "total_revenue": 100},
                {"period_end": date(2025, 6, 30), "total_revenue": 0},
            ],
        }
        assert signals.fundamental_evidence(None, quarterly) == []


class TestNewsEvidence:
    def test_no_news_produces_no_row(self):
        assert signals.news_evidence([]) == []

    def test_news_never_casts_a_direction_vote(self):
        """Sistemde ölçülmüş bir duygu skoru yok (`sentiment` her satırda sabit
        "neutral"). Bir başlıktan yön çıkarmak, ölçmediğimiz bir şeyi ölçmüş
        gibi göstermek olurdu."""
        rows = signals.news_evidence([object(), object()])
        assert rows[0]["direction"] == signals.NEUTRAL
        assert rows[0]["value"] == 2

    def test_filings_are_counted_separately(self):
        class Item:
            def __init__(self, source):
                self.source = source

        rows = signals.news_evidence([Item("KAP"), Item("Dünya")])
        assert "1 KAP bildirimi" in rows[0]["text"]


class TestCombine:
    def _tech(self, direction, n=1):
        return [
            {"source": signals.TECHNICAL, "key": f"t{i}", "direction": direction,
             "value": 1, "text": "t"}
            for i in range(n)
        ]

    def _fund(self, direction, n=1):
        return [
            {"source": signals.FUNDAMENTAL, "key": f"f{i}", "direction": direction,
             "value": 1, "text": "f"}
            for i in range(n)
        ]

    def test_an_unmeasured_source_is_excluded_not_zeroed(self):
        """`risk/profile.py:score_from` ile birebir aynı kural: ölçülemeyen bir
        düşüşü "düşüş yok" saymak, geçmişi kısa olan enstrümanı ödüllendirmek
        olurdu."""
        result = signals.combine(self._tech(signals.UP, 2) + self._fund(signals.UP), "3M")
        assert result["lean"] == 1.0
        assert result["by_source"][signals.NEWS] is None

    def test_two_sources_disagreeing_land_in_the_middle(self):
        result = signals.combine(
            self._tech(signals.UP, 2) + self._fund(signals.DOWN, 2), "3M"
        )
        assert result["direction"] == "MIXED"

    def test_too_few_evidence_items_is_insufficient(self):
        result = signals.combine(self._tech(signals.UP) + self._fund(signals.UP), "3M")
        assert result["direction"] == "INSUFFICIENT"

    def test_one_source_alone_is_insufficient(self):
        """Tek kaynaktan gelen üç kanıt aslında tek bir şeyin üç görünümü
        olabiliyor."""
        result = signals.combine(self._tech(signals.UP, 5), "3M")
        assert result["direction"] == "INSUFFICIENT"

    def test_no_evidence_at_all(self):
        result = signals.combine([], "3M")
        assert result["direction"] == "INSUFFICIENT"
        assert result["lean"] == 0.0

    def test_the_horizon_changes_the_weighting(self):
        """Vade kısaldıkça fiyat hareketi, uzadıkça bilanço ağırlık kazanıyor."""
        evidence = self._tech(signals.UP, 2) + self._fund(signals.DOWN, 2)
        short = signals.combine(evidence, "1M")["lean"]
        long = signals.combine(evidence, "6M")["lean"]
        assert short > 0 > long

    def test_a_strong_lean_is_declared(self):
        result = signals.combine(
            self._tech(signals.UP, 3) + self._fund(signals.UP, 2), "3M"
        )
        assert result["direction"] == "UP_LEAN"

    def test_a_strong_negative_lean_is_declared(self):
        result = signals.combine(
            self._tech(signals.DOWN, 3) + self._fund(signals.DOWN, 2), "3M"
        )
        assert result["direction"] == "DOWN_LEAN"


class TestEvaluate:
    def test_a_horizon_beyond_the_evidence_is_refused(self):
        """Elimizdeki ölçümler iki yıla konuşamaz ve uydurmaktansa reddetmek
        gerekiyor -- `technicals`in yetersiz bar kuralıyla aynı."""
        out = signals.evaluate("THYAO", "2Y", technicals.compute(_rising()))
        assert out["direction"] == "OUT_OF_RANGE"
        assert out["narrative"] == signals.OUT_OF_RANGE_TR
        assert out["evidence"] == []
        assert out["lean"] is None

    def test_a_short_history_cannot_produce_a_reading(self):
        """27 barlık bir sembolde `compute()` zaten `sma_50/200 = None`
        döndürüyor; kapı kendiliğinden devreye giriyor."""
        out = signals.evaluate("YENI", "3M", technicals.compute(_bars([10.0] * 27)))
        assert out["direction"] == "INSUFFICIENT"
        assert "27 işlem günü" in out["narrative"]

    def test_the_reading_names_what_it_could_not_measure(self):
        out = signals.evaluate("YENI", "3M", technicals.compute(_bars([10.0] * 27)))
        assert out["coverage"]["missing"]
        assert "Ölçülemeyen" in out["narrative"]

    def test_a_full_reading_carries_its_hedge(self):
        out = signals.evaluate(
            "THYAO", "3M", technicals.compute(_rising()),
            {"return_on_equity": 0.4, "profit_margin": 0.3, "revenue_growth": 0.4},
        )
        assert out["direction"] == "UP_LEAN"
        assert technicals.HEDGE_TR in out["narrative"]

    def test_a_mixed_reading_has_no_forward_clause(self):
        """MIXED'te devam cümlesi YOKTUR: devam edecek bir görünüm de yok."""
        out = signals.evaluate(
            "X", "3M", technicals.compute(_rising()),
            {"return_on_equity": -0.5, "profit_margin": -0.3, "revenue_growth": -0.4},
        )
        assert out["direction"] == "MIXED"
        assert "beklenebilir" not in out["narrative"]

    def test_the_horizon_assumption_is_stated(self):
        """"3 aylık okuma" diyen bir cevap, o vadeye nasıl varıldığını
        göstermeden bir otorite iddiası taşır."""
        out = signals.evaluate("X", "3M", technicals.compute(_rising()))
        assert "varsayım" in out["horizon_note"]

    def test_observations_are_reported(self):
        out = signals.evaluate("X", "1M", technicals.compute(_rising(260)))
        assert out["coverage"]["observations"] == 260

    def test_a_reading_without_a_bar_count_still_reads(self):
        """`observations` çağırandan geliyor; taşımayan bir girdi okumayı
        düşürmemeli, yalnızca o cümleyi atlamalı."""
        out = signals.evaluate("X", "3M", {})
        assert out["direction"] == "INSUFFICIENT"
        assert "işlem günü" not in out["narrative"]

    def test_a_full_reading_without_a_bar_count(self):
        out = signals.evaluate(
            "X", "3M",
            {"sma_50": 120.0, "sma_200": 100.0, "trend": "UPTREND",
             "week52_position_pct": 90.0},
            {"return_on_equity": 0.4, "profit_margin": 0.3},
        )
        assert out["direction"] == "UP_LEAN"
        assert "işlem günü ölçüldü" not in out["narrative"]

    def test_an_empty_period_list_with_the_year_flag_set(self):
        """Bayrak dolu ama seri boş: sağlayıcıdan gelen tutarsız bir gövde
        okumayı düşürmemeli."""
        assert signals.fundamental_evidence(
            None, {"year_ago_available": True, "periods": []}
        ) == []

    def test_news_presence_adds_its_caveat(self):
        class Item:
            source = "Dünya"

        out = signals.evaluate(
            "X", "3M", technicals.compute(_rising()),
            {"return_on_equity": 0.4}, None, [Item()],
        )
        assert signals.NEWS_CAVEAT_TR in out["narrative"]


class TestWording:
    """Motorun ürettiği HİÇBİR cümle uygunluk kurallarına takılmamalı.

    Bu, "geçmesi tesadüf değil" iddiasını sabitleyen yer. Uygunluk kapısı
    yalnızca sohbet taslağına uygulanıyor (`orchestrator.compliance_gate_node`);
    bu modülün beslediği REST uçları oradan geçmiyor, dolayısıyla kuralın
    çalıştığını garanti eden başka hiçbir mekanizma yok.
    """

    def _all_narratives(self):
        cases = []
        strong_up = {"return_on_equity": 0.4, "profit_margin": 0.3, "revenue_growth": 0.4}
        strong_down = {"return_on_equity": -0.4, "profit_margin": -0.3,
                       "revenue_growth": -0.4, "debt_to_equity": 500.0}
        quarterly_up = {
            "previous_is_adjacent": True, "year_ago_available": True,
            "periods": [
                {"period_end": date(2026, 6, 30), "label": "2026Q2",
                 "net_income": 120, "total_revenue": 200},
                {"period_end": date(2026, 3, 31), "net_income": 100, "total_revenue": 190},
                {"period_end": date(2025, 12, 31), "net_income": 90, "total_revenue": 150},
                {"period_end": date(2025, 9, 30), "net_income": 80, "total_revenue": 120},
                {"period_end": date(2025, 6, 30), "net_income": 70, "total_revenue": 100},
            ],
        }

        class Item:
            source = "KAP"

        for horizon in list(signals.HORIZONS) + ["2Y"]:
            for bars in (_rising(), _falling(), _bars([10.0] * 27), []):
                for fundamentals in (None, strong_up, strong_down):
                    cases.append(signals.evaluate(
                        "THYAO", horizon, technicals.compute(bars),
                        fundamentals, quarterly_up, [Item()],
                    )["narrative"])
        return [c for c in cases if c]

    def test_no_narrative_trips_any_advice_or_guarantee_rule(self):
        from app.modules.compliance import rules

        watched = {
            "ADV-001", "ADV-002", "ADV-003",
            "GUA-001", "GUA-002", "GUA-003",
            "SUI-001", "EXE-001", "SOL-001",
        }
        checked = [r for r in rules.RULES if r.rule_id in watched]
        assert checked, "kural paketi bulunamadı"
        for narrative in self._all_narratives():
            for rule in checked:
                assert not rule.regex.search(narrative), f"{rule.rule_id}: {narrative}"

    def test_every_forward_clause_carries_its_hedge(self):
        """Koşullu okuma ve çekincesi ayrılamaz: cümleyi ikiye bölüp yalnızca
        ilk yarısını göstermek, koşulu düşürüp iddiayı bırakmak olur."""
        for narrative in self._all_narratives():
            if "beklenebilir" in narrative:
                assert technicals.HEDGE_TR in narrative, narrative

    def test_no_narrative_names_a_target_price(self):
        for narrative in self._all_narratives():
            lowered = narrative.lower()
            for banned in ("hedef fiyat", "hedef seviye", "tl'ye ulaş", "değerinde"):
                assert banned not in lowered, f"{banned}: {narrative}"

    def test_no_narrative_gives_a_directive(self):
        for narrative in self._all_narratives():
            lowered = narrative.lower()
            for banned in ("almalı", "satmalı", "alın", "satın", "öneri",
                           "tavsiye", "kaçırmayın", "en iyi", "ucuz", "pahalı"):
                assert banned not in lowered, f"{banned}: {narrative}"


class TestNightlyRefresh:
    """Gecelik toplu hesap. Tek sembol sorulduğunda okuma TAZE hesaplanıyor;
    bu iş yalnızca 1.011 enstrümanı istek anında hesaplamamak için var."""

    def _product(self, symbol="ASELS"):
        from types import SimpleNamespace

        return SimpleNamespace(id=f"p-{symbol}", symbol=symbol)

    def _patch(self, mocker, products, side_effect=None):
        import app.core.database as database
        from app.modules.investment import market_service
        from app.modules.market import service as market_module

        db = mocker.MagicMock()
        db.query.return_value.filter.return_value.all.return_value = products
        mocker.patch.object(database, "SessionLocal", return_value=db)
        mocker.patch.object(
            market_service, "candle_series",
            side_effect=side_effect or (lambda *a, **k: []),
        )
        mocker.patch.object(market_service, "fundamentals_for", return_value=None)
        mocker.patch.object(market_service, "quarterly_for", return_value=None)
        mocker.patch.object(market_module, "latest_news", return_value=[])
        stored = mocker.patch.object(
            market_module, "store_direction_signals", side_effect=lambda d, rows: len(rows)
        )
        return db, stored

    @pytest.mark.asyncio
    async def test_every_horizon_is_written(self, mocker):
        _, stored = self._patch(mocker, [self._product()])
        result = await signals.refresh_all_signals()
        assert set(result) == set(signals.HORIZONS)
        assert stored.call_count == len(signals.HORIZONS)

    @pytest.mark.asyncio
    async def test_one_bad_instrument_does_not_lose_the_rest(self, mocker):
        """1.011 enstrümanın birinde beklenmedik bir değer, tarama tablosunun
        tamamının boş kalması demek olmamalı."""
        def series(db, symbol, limit=None):
            if symbol == "PATLAK":
                raise ValueError("bozuk seri")
            return []

        _, stored = self._patch(
            mocker, [self._product("PATLAK"), self._product("ASELS")], series
        )
        result = await signals.refresh_all_signals()
        assert result["3M"] == 1, "sağlam enstrüman yazılmalı"

    @pytest.mark.asyncio
    async def test_an_empty_universe_writes_nothing(self, mocker):
        _, stored = self._patch(mocker, [])
        result = await signals.refresh_all_signals()
        assert result == {horizon: 0 for horizon in signals.HORIZONS}

    @pytest.mark.asyncio
    async def test_the_session_is_closed(self, mocker):
        db, _ = self._patch(mocker, [])
        await signals.refresh_all_signals()
        db.close.assert_called_once()
