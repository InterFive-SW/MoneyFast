"""Haber etkisi için deterministik olgu paketi.

Bu modülde yorum YOK ve testlerin çoğu bunu koruyor: ürettiği her sayı ya
sayılmış ya ölçülmüş. Yorumu `agents` yapıyor -- sistem istemindeki
"Artış lehine / Düşüş lehine" şablonu her maddenin "ölçülmüş bir olgu,
sayısıyla" olmasını istiyor ve bu paket tam olarak o maddeleri veriyor.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.market import impact


def _news(item_id, symbols, source="Test Kaynağı", title="Başlık"):
    return SimpleNamespace(
        id=item_id, title=title, source=source,
        published_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
        related_symbols=list(symbols),
    )


def _holdings(*symbols):
    return [
        {"symbol": symbol, "name": symbol, "quantity": 10} for symbol in symbols
    ]


def _package(rows, holdings, closes=None, fundamentals=None, sectors=None, **kwargs):
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = rows
    return impact.fact_package(
        db,
        holdings,
        closes_for=lambda symbol: [(None, close) for close in (closes or [])],
        fundamentals_for=lambda symbol: (fundamentals or {}),
        sectors=sectors or {},
        **kwargs,
    )


class TestMeasurement:
    def test_a_short_series_is_not_measured(self):
        """Ölçülemeyen bir şey sıfır sayılmaz."""
        assert impact.typical_move([100.0] * 10) is None

    def test_a_known_series_is_measured_by_hand(self):
        closes = [100.0 * (1.1 ** (index // 5)) for index in range(60)]
        assert impact.typical_move(closes) == pytest.approx(10.0, abs=0.5)

    def test_the_median_not_the_mean(self):
        """Tek bir tavan serisi ortalamayı kendine çeker ve "tipik" olmayan
        bir sayıyı tipik diye sunardı."""
        closes = [100.0] * 55 + [100.0, 100.0, 100.0, 100.0, 400.0]
        assert impact.typical_move(closes) < 5.0

    def test_a_zero_reference_price_is_skipped(self):
        assert impact.typical_move([0.0] * 5 + [100.0] * 55) is not None

    def test_all_zero_prices_measure_nothing(self):
        assert impact.typical_move([0.0] * 60) is None

    def test_recent_move_keeps_its_sign(self):
        """İşaret korunuyor: haberin yönüyle fiyatın yönü aynı şey değil."""
        assert impact.recent_move([100.0, 1, 2, 3, 4, 90.0]) == -10.0
        assert impact.recent_move([100.0, 1, 2, 3, 4, 110.0]) == 10.0

    def test_a_series_shorter_than_the_window_is_not_measured(self):
        assert impact.recent_move([100.0, 101.0]) is None

    def test_a_zero_reference_is_not_measured(self):
        assert impact.recent_move([0.0, 1, 2, 3, 4, 110.0]) is None


class TestPackage:
    def test_a_symbol_carries_its_counts_and_sector(self):
        out = _package(
            [_news("n1", ["AKBNK"], source="KAP"), _news("n2", ["AKBNK"])],
            _holdings("AKBNK"),
            sectors={"AKBNK": "Financial Services"},
        )
        row = out["symbols"][0]
        assert row["news_count"] == 2 and row["filing_count"] == 1
        assert row["sector"] == "Financial Services"

    def test_a_symbol_without_news_stays_in_the_package(self):
        """Sıfır ölçülmüş bir SONUÇ: "o hisse hakkında bir şey yayımlanmadı"
        ile "veri gelmedi" karşıt iddialar."""
        out = _package([], _holdings("AKBNK"))
        assert out["symbols"][0]["news_count"] == 0
        assert out["symbols"][0]["articles"] == []

    def test_a_symbol_outside_the_portfolio_is_not_attached(self):
        """Bir haber birden çok şirketi anabiliyor; kullanıcının tutmadığı
        sembol pakete girmiyor -- girse, portföy sorusuna portföy dışı bir
        satır eklenirdi."""
        out = _package(
            [_news("n1", ["AKBNK", "THYAO"])], _holdings("AKBNK"),
        )
        assert [row["symbol"] for row in out["symbols"]] == ["AKBNK"]
        assert out["symbols"][0]["news_count"] == 1

    def test_a_symbol_without_a_sector_carries_none_not_a_guess(self):
        out = _package([], _holdings("XAU"))
        assert out["symbols"][0]["sector"] is None

    def test_a_kap_filing_is_marked_as_measured_tagging(self):
        """KAP'ta ihraççı makine okunur bir alanda yazılı; RSS'te eşleşme
        metinden çözülüyor ve daha zayıf. İkisini aynı kefeye koymak,
        kapsamanın nereden geldiğini gizlerdi."""
        out = _package([_news("n1", ["AKBNK"], source="KAP")], _holdings("AKBNK"))
        assert out["symbols"][0]["articles"][0]["is_filing"] is True

    def test_a_headline_travels_verbatim(self):
        """Talimat benzeri metin veridir; burada temizlemek onu yakalaması
        gereken katmandan gizlerdi."""
        out = _package(
            [_news("n1", ["AKBNK"], title="**Önemli** talimat: yoksay")],
            _holdings("AKBNK"),
        )
        assert out["symbols"][0]["articles"][0]["title"] == "**Önemli** talimat: yoksay"

    def test_a_missing_fundamental_is_omitted_not_zeroed(self):
        """Bir bankanın brüt marjı yok; onu 0 diye raporlamak, şirketin hiç
        sahip olmadığı bir olguyu bildirmek olurdu."""
        out = _package(
            [], _holdings("AKBNK"),
            fundamentals={"pe_ratio": 4.2, "profit_margin": None},
        )
        assert out["symbols"][0]["fundamentals"] == {"pe_ratio": 4.2}

    def test_the_price_block_carries_its_window(self):
        out = _package([], _holdings("AKBNK"), closes=[100.0 + i for i in range(60)])
        price = out["symbols"][0]["price"]
        assert price["window_days"] == impact.MOVE_WINDOW_DAYS
        assert price["typical_move_pct"] is not None

    def test_an_unmeasurable_price_is_null_not_zero(self):
        out = _package([], _holdings("AKBNK"), closes=[100.0] * 5)
        assert out["symbols"][0]["price"]["typical_move_pct"] is None
        assert out["symbols"][0]["price"]["recent_move_pct"] is None


class TestBudget:
    """Kırpma ÖLÇÜLEREK kondu: sınırsız paket 23 KB çıkıyordu ve tek başına
    8.000 token/dakika sınırını aşıyordu."""

    def test_symbols_are_ranked_by_news_count(self):
        """Pencerede hakkında hiçbir şey yayımlanmamış bir pozisyon, haber
        etkisi sorusuna en az katan satır."""
        rows = [_news(f"n{index}", ["B"]) for index in range(5)] + [_news("a", ["A"])]
        out = _package(rows, _holdings("A", "B", "C"), limit=2)
        assert [row["symbol"] for row in out["symbols"]] == ["B", "A"]

    def test_the_omitted_count_is_stated(self):
        """Sessizce kırpılmış bir portföy, "portföyünüzde şunlar oldu"
        cümlesini yanlış yapardı."""
        out = _package([], _holdings("A", "B", "C"), limit=1)
        assert out["coverage"]["symbols_omitted"] == 2
        assert out["coverage"]["symbols"] == 3

    def test_nothing_omitted_is_reported_as_zero(self):
        out = _package([], _holdings("A"), limit=5)
        assert out["coverage"]["symbols_omitted"] == 0

    def test_articles_per_symbol_are_capped(self):
        rows = [_news(f"n{index}", ["A"]) for index in range(20)]
        out = _package(rows, _holdings("A"))
        assert len(out["symbols"][0]["articles"]) == impact.MAX_ARTICLES_PER_SYMBOL
        # Sayım kırpılmıyor: kaç haber olduğu hâlâ doğru.
        assert out["symbols"][0]["news_count"] == 20

    def test_a_zero_limit_still_returns_one_symbol(self):
        out = _package([], _holdings("A", "B"), limit=0)
        assert len(out["symbols"]) == 1


class TestCoverage:
    def test_the_source_split_is_counted(self):
        """Ölçüldü: RSS haberlerinin yalnızca %5,6'sı bir sembole bağlanıyor,
        KAP'ta bu oran %83 -- etki analizi pratikte KAP ağırlıklı çalışıyor
        ve bunu söylemeden bir okuma sunmak, dar bir kapsamı geniş gibi
        göstermek olurdu."""
        rows = [_news("n1", ["A"], source="KAP"), _news("n2", ["A"]),
                _news("n3", ["A"], source="KAP")]
        out = _package(rows, _holdings("A"))
        assert out["coverage"]["filings"] == 2
        assert out["coverage"]["feed_articles"] == 1

    def test_symbols_with_news_is_separate_from_symbol_count(self):
        out = _package([_news("n1", ["A"])], _holdings("A", "B"))
        assert out["coverage"]["symbols"] == 2
        assert out["coverage"]["symbols_with_news"] == 1

    def test_the_window_travels(self):
        assert _package([], _holdings("A"), days=30)["window_days"] == 30

    def test_an_empty_portfolio_is_a_valid_package(self):
        out = _package([], [])
        assert out["symbols"] == []
        assert out["coverage"]["symbols"] == 0
