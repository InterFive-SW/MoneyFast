"""Haber etki yargılarının toplanması ve cümleye dönüşmesi.

En önemli iki test: `TestAcceptable` (modelin yazdığı gerekçe uygunluk
kurallarına karşı taranıyor -- bu metin REST üzerinden kullanıcıya gidiyor
ve sohbetin uygunluk kapısından GEÇMİYOR) ve `TestWording` (kodun kurduğu
cümlelerin aynı regex'lere takılmaması). Cümlenin kurallardan geçmesi
tesadüf olmamalı.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.modules.compliance.rules import RULES
from app.modules.market import news_impact as ni


def _row(symbol="ASELS", direction=ni.UP, scope=ni.DIRECT, magnitude="MEDIUM",
         confidence=0.7, mechanism="Sözleşme tutarı yıllık ihracata ekleniyor.",
         news_id="n1", published_at=None):
    return SimpleNamespace(
        symbol=symbol, direction=direction, scope=scope, magnitude=magnitude,
        confidence=confidence, mechanism=mechanism, news_id=news_id,
        published_at=published_at or datetime(2026, 9, 7, tzinfo=timezone.utc),
    )


class TestAcceptable:
    def test_an_empty_mechanism_is_refused(self):
        assert ni.acceptable("") is False
        assert ni.acceptable(None) is False

    def test_a_bare_label_is_refused(self):
        """Ölçülen gerçek çıktı: şirketin nasıl etkilendiğini hiç söylemeyen
        bir isim tamlaması."""
        assert ni.acceptable("Yönetim kurulu değişikliği") is False

    def test_the_shortest_measured_real_mechanism_passes(self):
        """Eşik gerçek bir mekanizma cümlesini elemiyor -- ölçülen en kısası."""
        assert ni.acceptable("Petrol fiyatlarındaki düşüş XOM'u etkiliyor.") is True

    def test_advice_wording_drops_the_row(self):
        assert ni.acceptable(
            "Bu gelişme sonrasında hisseyi almanızı öneririm çünkü talep artıyor."
        ) is False

    def test_a_guarantee_drops_the_row(self):
        assert ni.acceptable(
            "Sözleşme sayesinde hisse kesinlikle yükselecek diyebiliriz burada."
        ) is False

    def test_a_low_severity_finding_does_not_drop_the_row(self):
        """Yalnızca CRITICAL ve HIGH düşürüyor: her bulguyu düşürmek, kural
        paketinin LOW seviyesini BLOCK gibi davranan bir şeye çevirirdi."""
        low = [rule for rule in RULES if rule.severity == "LOW"]
        assert low, "kural paketinde LOW seviye yoksa bu test anlamını yitirir"


class TestTitleKey:
    def test_syndicated_copies_collapse(self):
        """Aynı ajans haberi farklı istasyon kuyruklarıyla geliyor."""
        assert ni.title_key("Oil Prices Hit 6-Week High | NewsRadio WIOD") == \
               ni.title_key("Oil Prices Hit 6-Week High | Talk Radio 1190")

    def test_a_kap_suffix_is_kept(self):
        """KAP başlığındaki uzun tireden sonrası haberin KENDİSİ; atılsaydı
        aynı şirketin aynı gündeki iki bildirimi tek gelişme sayılırdı."""
        first = ni.title_key("AKSİGORTA A.Ş. — Özel Durum Açıklaması")
        second = ni.title_key("AKSİGORTA A.Ş. — Pay Alım Satım Bildirimi")
        assert first != second

    def test_an_empty_title_is_an_empty_key(self):
        assert ni.title_key("") == ""
        assert ni.title_key(None) == ""


class TestMeasurement:
    def test_a_short_series_is_not_measured(self):
        """Ölçülemeyen bir şey sıfır sayılmaz."""
        assert ni.typical_move([100.0] * 10) is None

    def test_a_flat_series_has_a_zero_typical_move(self):
        assert ni.typical_move([100.0] * 60) == 0.0

    def test_a_known_series_is_measured_by_hand(self):
        """Her beş barda %10 artan seri: tipik hareket %10."""
        closes = [100.0 * (1.1 ** (index // 5)) for index in range(60)]
        assert ni.typical_move(closes) == pytest.approx(10.0, abs=0.5)

    def test_a_zero_reference_price_is_skipped(self):
        """Sıfır fiyatlı bir bar bölme hatası vermez, o pencere atlanır."""
        closes = [0.0] * 5 + [100.0] * 55
        assert ni.typical_move(closes) is not None

    def test_all_zero_prices_measure_nothing(self):
        assert ni.typical_move([0.0] * 60) is None

    def test_recent_move_keeps_its_sign(self):
        """İşaret korunuyor: yönün fiyatla aynı olup olmadığı okunabilmeli."""
        assert ni.recent_move([100.0, 1, 2, 3, 4, 90.0]) == -10.0
        assert ni.recent_move([100.0, 1, 2, 3, 4, 110.0]) == 10.0

    def test_a_series_shorter_than_the_window_is_not_measured(self):
        assert ni.recent_move([100.0, 101.0]) is None

    def test_a_zero_reference_is_not_measured(self):
        assert ni.recent_move([0.0, 1, 2, 3, 4, 110.0]) is None


class TestSymbolEntry:
    def test_counts_and_reasons_are_carried(self):
        entry = ni.symbol_entry("ASELS", [_row(), _row(direction=ni.DOWN, news_id="n2")])
        assert entry["counts"] == {ni.UP: 1, ni.DOWN: 1, ni.NEUTRAL: 0}
        assert {reason["newsId"] for reason in entry["reasons"]} == {"n1", "n2"}

    def test_reasons_are_ordered_by_declared_confidence(self):
        entry = ni.symbol_entry("ASELS", [
            _row(news_id="low", confidence=0.2),
            _row(news_id="high", confidence=0.9),
        ])
        assert entry["reasons"][0]["newsId"] == "high"

    def test_confidence_is_not_exposed(self):
        """Modelin beyanı bir ölçüm değil; sıralamada kullanılıyor,
        gösterilmiyor."""
        entry = ni.symbol_entry("ASELS", [_row()])
        assert "confidence" not in entry["reasons"][0]

    def test_an_all_neutral_symbol_is_not_called_two_sided(self):
        """Ölçülen hata: iki NEUTRAL bildirim 'iki yöne birden' yazılıyordu."""
        entry = ni.symbol_entry("VESTL", [_row(direction=ni.NEUTRAL),
                                          _row(direction=ni.NEUTRAL, news_id="n2")])
        assert "iki yöne birden" not in entry["sentence"]
        assert "yön belirtmeyen" in entry["sentence"]

    def test_a_contested_symbol_is_called_two_sided(self):
        entry = ni.symbol_entry("NVDA", [_row(), _row(direction=ni.DOWN, news_id="n2")])
        assert "iki yöne birden" in entry["sentence"]

    def test_a_leaning_symbol_states_its_side(self):
        assert "yükseliş yönünde" in ni.symbol_entry("ASELS", [_row()])["sentence"]
        assert "düşüş yönünde" in ni.symbol_entry(
            "ASELS", [_row(direction=ni.DOWN)])["sentence"]

    def test_a_single_spillover_reads_as_one(self):
        """'Bunların 1 tanesi' tek satırlık bir özette yanlış Türkçe."""
        entry = ni.symbol_entry("AAPL", [_row(scope=ni.SPILLOVER)])
        assert "Bunların" not in entry["sentence"]
        assert "Haber doğrudan bu şirket hakkında değil" in entry["sentence"]

    def test_only_spillovers_say_so_in_plural(self):
        entry = ni.symbol_entry("AAPL", [
            _row(scope=ni.SPILLOVER), _row(scope=ni.SPILLOVER, news_id="n2")])
        assert "hiçbiri doğrudan bu şirket hakkında değil" in entry["sentence"]

    def test_a_mix_counts_the_spillovers(self):
        entry = ni.symbol_entry("NVDA", [_row(), _row(scope=ni.SPILLOVER, news_id="n2")])
        assert "Bunların 1 tanesi" in entry["sentence"]
        assert entry["directCount"] == 1 and entry["spilloverCount"] == 1

    def test_no_series_means_no_measurement_sentence(self):
        entry = ni.symbol_entry("ASELS", [_row()])
        assert entry["measured"] is None
        assert "Ölçülen:" not in entry["sentence"]

    def test_a_short_series_measures_nothing_and_says_nothing(self):
        """Yetersiz bar için 'hareket %0' demek, ölçülmemişi ölçülmüş
        göstermek olurdu."""
        entry = ni.symbol_entry("ASELS", [_row()], closes=[100.0] * 10)
        assert entry["measured"] is None
        assert "Ölçülen:" not in entry["sentence"]

    def test_a_measured_series_is_stated_with_both_numbers(self):
        closes = [100.0 + index for index in range(60)]
        entry = ni.symbol_entry("ASELS", [_row()], closes=closes)
        assert entry["measured"]["typicalMovePct"] is not None
        assert "Ölçülen:" in entry["sentence"]
        assert "tipik olarak" in entry["sentence"]

    def test_a_falling_series_is_worded_as_falling(self):
        closes = [200.0 - index for index in range(60)]
        entry = ni.symbol_entry("ASELS", [_row()], closes=closes)
        assert "geriledi" in entry["sentence"]


class TestPortfolioHeadline:
    def test_an_empty_portfolio_says_so(self):
        text = ni.portfolio_headline([], 24)
        assert "bulunmuyor" in text and "24" in text

    def test_each_shape_is_counted_separately(self):
        entries = [
            ni.symbol_entry("A", [_row()]),
            ni.symbol_entry("B", [_row(direction=ni.DOWN)]),
            ni.symbol_entry("C", [_row(), _row(direction=ni.DOWN, news_id="n2")]),
            ni.symbol_entry("D", [_row(direction=ni.NEUTRAL)]),
        ]
        text = ni.portfolio_headline(entries, 24)
        assert "1 tanesi yükseliş yönünde" in text
        assert "1 tanesi düşüş yönünde" in text
        assert "1 tanesi iki yöne birden" in text
        assert "1 tanesi yön belirtmeyen" in text


    def test_only_the_present_shapes_are_named(self):
        """Sıfır olan bir kategori cümlede HİÇ geçmiyor: '0 tanesi düşüş
        yönünde' demek, olmayan bir şeyi sayıya dökmek olurdu."""
        text = ni.portfolio_headline([ni.symbol_entry("A", [_row()])], 24)
        assert text.endswith("1 tanesi yükseliş yönünde okundu.")

    def test_a_portfolio_with_no_upside_never_names_one(self):
        text = ni.portfolio_headline(
            [ni.symbol_entry("A", [_row(direction=ni.DOWN)])], 24)
        assert "yükseliş" not in text
        assert text.endswith("1 tanesi düşüş yönünde okundu.")


class TestTally:
    def test_an_unknown_direction_is_not_counted(self):
        """Modelin tanınmayan bir yön yazması satırı düşürmüyor ama sayıma da
        girmiyor -- sayılmayan bir yön, uydurulmuş bir yönden iyidir."""
        entry = ni.symbol_entry("ASELS", [_row(direction="SIDEWAYS")])
        assert entry["counts"] == {ni.UP: 0, ni.DOWN: 0, ni.NEUTRAL: 0}


class TestMarketEntries:
    def test_symbols_are_ranked_by_comment_count(self):
        """Modelin beyan ettiği güvene göre değil: beyan bir ölçüm değil."""
        rows = [
            _row(symbol="AAA", confidence=0.99),
            _row(symbol="BBB", confidence=0.1),
            _row(symbol="BBB", confidence=0.1, news_id="n2"),
        ]
        entries = ni.market_entries(rows)
        assert [entry["symbol"] for entry in entries] == ["BBB", "AAA"]

    def test_the_limit_is_honoured(self):
        rows = [_row(symbol=f"S{index}") for index in range(20)]
        assert len(ni.market_entries(rows, limit=5)) == 5

    def test_a_zero_limit_still_returns_a_row(self):
        rows = [_row(symbol="AAA")]
        assert len(ni.market_entries(rows, limit=0)) == 1

    def test_grouping_keeps_every_row(self):
        rows = [_row(symbol="AAA"), _row(symbol="AAA", news_id="n2"), _row(symbol="BBB")]
        grouped = ni.group_by_symbol(rows)
        assert len(grouped["AAA"]) == 2 and len(grouped["BBB"]) == 1


class TestWording:
    """Kodun kurduğu HİÇBİR cümle uygunluk kurallarına takılmamalı.

    `signals.TestWording` ile aynı gerekçe: bu cümleler REST üzerinden
    kullanıcıya gidiyor ve sohbetin uygunluk kapısından geçmiyor. Kuralları
    burada uygulamak, onları ikinci kez yazmadan kontrol altında tutuyor.
    """

    def _sentences(self):
        closes = [100.0 + index for index in range(60)]
        falling = [200.0 - index for index in range(60)]
        entries = [
            ni.symbol_entry("ASELS", [_row()], closes=closes),
            ni.symbol_entry("ASELS", [_row(direction=ni.DOWN)], closes=falling),
            ni.symbol_entry("ASELS", [_row(direction=ni.NEUTRAL)]),
            ni.symbol_entry("ASELS", [_row(), _row(direction=ni.DOWN, news_id="n2")]),
            ni.symbol_entry("AAPL", [_row(scope=ni.SPILLOVER)]),
            ni.symbol_entry("AAPL", [_row(scope=ni.SPILLOVER),
                                     _row(scope=ni.SPILLOVER, news_id="n2")]),
        ]
        return (
            [entry["sentence"] for entry in entries]
            + [ni.portfolio_headline(entries, 24), ni.portfolio_headline([], 24)]
            + [ni.DISCLAIMER_TR]
        )

    @pytest.mark.parametrize("rule", [rule for rule in RULES], ids=lambda r: r.rule_id)
    def test_no_generated_sentence_trips_a_rule(self, rule):
        for sentence in self._sentences():
            assert not rule.regex.search(sentence), f"{rule.rule_id}: {sentence}"

    def test_the_disclaimer_says_it_is_a_model_reading(self):
        assert "yapay zeka" in ni.DISCLAIMER_TR
        assert "yatırım tavsiyesi değildir" in ni.DISCLAIMER_TR


# ── Depoya dokunan yollar ───────────────────────────────────────────────────
#
# Gerçek bir veritabanı yok (paketin geri kalanında da yok): okunan zincirler
# taklit ediliyor. Burada sabitlenen şey SQL değil, davranış -- hangi satırın
# yazıldığı, hangisinin elendiği ve bir hatanın turu düşürüp düşürmediği.

from unittest.mock import AsyncMock, MagicMock  # noqa: E402

from sqlalchemy.orm import Session  # noqa: E402


class TestStoreImpacts:
    def test_an_empty_list_writes_nothing(self):
        db = MagicMock(spec=Session)
        assert ni.store_impacts(db, "n1", datetime.now(timezone.utc), []) == 0
        db.execute.assert_not_called()

    def test_an_unacceptable_mechanism_is_dropped(self):
        db = MagicMock(spec=Session)
        written = ni.store_impacts(db, "n1", datetime.now(timezone.utc), [
            {"symbol": "ASELS", "direction": ni.UP, "mechanism": "Kısa"},
        ])
        assert written == 0
        db.execute.assert_not_called()

    def test_a_row_without_a_symbol_is_dropped(self):
        db = MagicMock(spec=Session)
        assert ni.store_impacts(db, "n1", datetime.now(timezone.utc), [
            {"direction": ni.UP, "mechanism": "Talep artışı marjı yukarı çekiyor."},
        ]) == 0

    def test_a_row_without_a_direction_is_dropped(self):
        db = MagicMock(spec=Session)
        assert ni.store_impacts(db, "n1", datetime.now(timezone.utc), [
            {"symbol": "ASELS", "mechanism": "Talep artışı marjı yukarı çekiyor."},
        ]) == 0

    def test_a_valid_row_is_written_with_its_defaults(self):
        db = MagicMock(spec=Session)
        written = ni.store_impacts(db, "n1", datetime(2026, 9, 7, tzinfo=timezone.utc), [
            {"symbol": "ASELS", "direction": ni.UP,
             "mechanism": "Talep artışı şirketin marjını yukarı çekiyor."},
        ], model="test-model")
        assert written == 1
        # Yazılan gövde varsayılanlarıyla birlikte sabitleniyor: kapsam
        # belirtilmemişse DOĞRUDAN, büyüklük belirtilmemişse LOW. Modelin
        # atladığı bir alanın sessizce "yüksek" olması, beyan edilmemiş bir
        # iddiayı beyan edilmiş gibi saklardı.
        (written_rows,) = [
            call.args[0].compile().params for call in db.execute.call_args_list
        ]
        assert written_rows["scope_m0"] == ni.DIRECT
        assert written_rows["magnitude_m0"] == "LOW"
        assert written_rows["model_m0"] == "test-model"


class TestPendingNews:
    def _db(self, rows, judged_titles=()):
        db = MagicMock(spec=Session)
        judged = MagicMock()
        judged.all.return_value = [(title,) for title in judged_titles]
        pending = MagicMock()
        pending.scalars.return_value.all.return_value = rows
        db.execute.side_effect = [judged, pending]
        return db

    def _item(self, item_id, title, symbols=()):
        return SimpleNamespace(id=item_id, title=title, related_symbols=list(symbols),
                               summary="", source="Test",
                               published_at=datetime.now(timezone.utc))

    def test_syndicated_copies_within_a_batch_are_dropped(self):
        rows = [self._item("a", "Oil Prices Hit High | WIOD"),
                self._item("b", "Oil Prices Hit High | WILM"),
                self._item("c", "Farklı bir haber")]
        picked = ni.pending_news(self._db(rows), limit=10)
        assert [item.id for item in picked] == ["a", "c"]

    def test_a_copy_of_an_already_judged_item_is_dropped(self):
        """Bu olmadan aynı ajans haberi her turda bir kopyasıyla yeniden
        yargılanırdı."""
        rows = [self._item("a", "Oil Prices Hit High | WIOD")]
        db = self._db(rows, judged_titles=["Oil Prices Hit High | Talk Radio"])
        assert ni.pending_news(db, limit=10) == []

    def test_the_limit_stops_the_scan(self):
        rows = [self._item(str(index), f"Haber {index}") for index in range(10)]
        assert len(ni.pending_news(self._db(rows), limit=3)) == 3

    def test_a_zero_limit_still_asks_for_one(self):
        rows = [self._item("a", "Haber")]
        assert len(ni.pending_news(self._db(rows), limit=0)) == 1

    def test_an_empty_title_does_not_collapse_rows(self):
        """Boş anahtar bir eşleşme değil: başlıksız iki haber aynı haber
        değildir."""
        rows = [self._item("a", ""), self._item("b", "")]
        assert len(ni.pending_news(self._db(rows), limit=10)) == 2


class TestImpactsSince:
    def _db(self, rows):
        db = MagicMock(spec=Session)
        chain = db.query.return_value.filter.return_value
        chain.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows
        chain.order_by.return_value.limit.return_value.all.return_value = rows
        return db

    def test_a_market_wide_read_asks_for_no_symbol(self):
        db = self._db([_row()])
        assert len(ni.impacts_since(db, symbols=None)) == 1

    def test_an_empty_portfolio_reads_nothing(self):
        """Boş bir sembol listesi 'süzgeç yok' demek DEĞİL: hiçbir şey
        tutmayan bir kullanıcıya piyasanın tamamını göstermek olurdu."""
        db = self._db([_row()])
        assert ni.impacts_since(db, symbols=[]) == []

    def test_a_portfolio_read_filters(self):
        db = self._db([_row()])
        assert len(ni.impacts_since(db, symbols=["ASELS", "", "ASELS"])) == 1


class TestUniverse:
    def test_the_news_own_tags_come_first_and_survive(self):
        """Havuza girmeyen bir hisse hakkındaki bildirim yorumlanabilmeli."""
        db = MagicMock(spec=Session)
        non_equity = MagicMock(); non_equity.all.return_value = [("USDTRY",)]
        pool = MagicMock(); pool.all.return_value = [("THYAO",), ("ASELS",)]
        db.execute.side_effect = [non_equity, pool]
        assert ni._universe(db, ["KRVGD", "", "KRVGD"]) == [
            "KRVGD", "USDTRY", "THYAO", "ASELS"]

    def test_duplicates_across_the_sources_collapse(self):
        db = MagicMock(spec=Session)
        non_equity = MagicMock(); non_equity.all.return_value = []
        pool = MagicMock(); pool.all.return_value = [("ASELS",)]
        db.execute.side_effect = [non_equity, pool]
        assert ni._universe(db, ["ASELS"]) == ["ASELS"]


class TestAnalyzeRecentNews:
    """Toplu iş. Sabitlenen şey: bir parçanın hatası turu düşürmüyor."""

    @pytest.fixture
    def wiring(self, monkeypatch):
        db = MagicMock(spec=Session)
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)
        monkeypatch.setattr(ni, "_universe", lambda *_args, **_kwargs: ["ASELS"])
        return db

    def _items(self, count):
        return [
            SimpleNamespace(id=f"n{index}", title=f"Haber {index}", summary="özet",
                            source="Test", related_symbols=["ASELS"],
                            published_at=datetime.now(timezone.utc))
            for index in range(count)
        ]

    def _client(self, responses):
        client = MagicMock()
        client.post = AsyncMock(side_effect=responses)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)
        return context

    def _response(self, results, model="m"):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"model": model, "results": results}
        return response

    @pytest.mark.asyncio
    async def test_an_empty_queue_is_not_an_error(self, wiring, monkeypatch):
        monkeypatch.setattr(ni, "pending_news", lambda *_a, **_k: [])
        assert await ni.analyze_recent_news() == {"analyzed": 0, "stored": 0, "failed": 0}

    @pytest.mark.asyncio
    async def test_returned_rows_are_stored(self, wiring, monkeypatch):
        monkeypatch.setattr(ni, "pending_news", lambda *_a, **_k: self._items(1))
        monkeypatch.setattr(
            "httpx.AsyncClient",
            lambda **_k: self._client([self._response([
                {"news_id": "n0", "impacts": [
                    {"symbol": "ASELS", "direction": ni.UP,
                     "mechanism": "Talep artışı şirketin marjını yukarı çekiyor."}]},
            ])]),
        )
        assert await ni.analyze_recent_news() == {"analyzed": 1, "stored": 1, "failed": 0}

    @pytest.mark.asyncio
    async def test_a_failed_chunk_does_not_stop_the_run(self, wiring, monkeypatch):
        """Yavaş bir istek o günün özetini tamamen boş bırakmamalı."""
        monkeypatch.setattr(ni, "JUDGE_CHUNK", 1)
        monkeypatch.setattr(ni, "pending_news", lambda *_a, **_k: self._items(2))
        monkeypatch.setattr(
            "httpx.AsyncClient",
            lambda **_k: self._client([
                RuntimeError("zaman aşımı"),
                self._response([{"news_id": "n1", "impacts": [
                    {"symbol": "ASELS", "direction": ni.UP,
                     "mechanism": "Talep artışı şirketin marjını yukarı çekiyor."}]}]),
            ]),
        )
        assert await ni.analyze_recent_news() == {"analyzed": 1, "stored": 1, "failed": 1}

    @pytest.mark.asyncio
    async def test_a_result_for_an_unknown_news_id_is_ignored(self, wiring, monkeypatch):
        """Sorulmayan bir haber hakkında dönen bir satır saklanmaz."""
        monkeypatch.setattr(ni, "pending_news", lambda *_a, **_k: self._items(1))
        monkeypatch.setattr(
            "httpx.AsyncClient",
            lambda **_k: self._client([self._response([{"news_id": "yok", "impacts": []}])]),
        )
        assert await ni.analyze_recent_news() == {"analyzed": 0, "stored": 0, "failed": 0}

    @pytest.mark.asyncio
    async def test_a_body_without_results_is_survivable(self, wiring, monkeypatch):
        monkeypatch.setattr(ni, "pending_news", lambda *_a, **_k: self._items(1))
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {}
        monkeypatch.setattr("httpx.AsyncClient", lambda **_k: self._client([response]))
        assert await ni.analyze_recent_news() == {"analyzed": 0, "stored": 0, "failed": 0}
