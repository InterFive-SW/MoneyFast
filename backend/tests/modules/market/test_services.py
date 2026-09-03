"""Market data storage.

Both stores are write-heavy paths driven by an external feed, so the tests
concentrate on what happens when the feed is wrong: an unknown symbol, a
repeated article, a batch with nothing usable in it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from sqlalchemy.orm import Session

from app.modules.investment import market_service
from app.modules.market import service as news_service
from app.modules.market import service as market_module_service

NOW = datetime.now(timezone.utc)


def db_with_products(*symbols) -> MagicMock:
    db = MagicMock(spec=Session)
    db.query.return_value.all.return_value = [
        SimpleNamespace(symbol=symbol, id=f"prod-{symbol}") for symbol in symbols
    ]
    db.execute.return_value = SimpleNamespace(rowcount=len(symbols))
    return db


class TestUpsertQuotes:
    def test_known_symbols_are_written(self):
        db = db_with_products("TEST-THYAO")
        written = market_service.upsert_quotes(
            db, [{"symbol": "TEST-THYAO", "price": 295.5, "market_timestamp": NOW}]
        )
        assert written == 1
        assert db.commit.called

    def test_unknown_symbol_is_skipped_not_created(self):
        """Creating a product from a ticker string would let a typo in a feed
        become a tradable instrument."""
        db = db_with_products("TEST-THYAO")
        written = market_service.upsert_quotes(
            db, [{"symbol": "NOT-A-PRODUCT", "price": 1.0, "market_timestamp": NOW}]
        )
        assert written == 0
        assert db.add.called is False

    def test_a_bad_row_does_not_stop_the_good_ones(self):
        db = db_with_products("TEST-THYAO")
        written = market_service.upsert_quotes(
            db,
            [
                {"symbol": "NOT-A-PRODUCT", "price": 1.0, "market_timestamp": NOW},
                {"symbol": "TEST-THYAO", "price": 295.5, "market_timestamp": NOW},
            ],
        )
        assert written == 1


class TestUpsertCandles:
    def test_empty_batch_makes_no_query(self):
        db = db_with_products("TEST-THYAO")
        assert market_service.upsert_candles(db, []) == 0
        assert db.execute.called is False

    def test_batch_of_only_unknown_symbols_makes_no_query(self):
        db = db_with_products("TEST-THYAO")
        rows = [{"symbol": "NOPE", "timestamp": NOW, "open": 1, "high": 2, "low": 1, "close": 2}]
        assert market_service.upsert_candles(db, rows) == 0
        assert db.execute.called is False

    def test_known_symbols_are_inserted_with_conflict_handling(self):
        """ON CONFLICT DO NOTHING is what makes a nightly backfill re-runnable
        without duplicating a single bar."""
        db = db_with_products("TEST-THYAO")
        rows = [
            {"symbol": "TEST-THYAO", "timestamp": NOW, "open": 1, "high": 2, "low": 1, "close": 2}
        ]
        assert market_service.upsert_candles(db, rows) == 1
        statement = str(db.execute.call_args.args[0])
        assert "ON CONFLICT" in statement.upper()


class TestFreshness:
    """`as_of` is when we OBSERVED the price, not the bar's own timestamp.

    The quote path requests daily bars, and a daily bar is stamped at the
    start of its trading day. Measuring delay from that stamp once reported a
    perfectly current price as 710 minutes stale, because the session had
    opened eleven hours earlier.
    """

    def test_measures_from_observation_not_from_the_bar_date(self):
        from datetime import timedelta

        midnight = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
        quotes = {"A": {"market_timestamp": midnight, "received_at": NOW - timedelta(minutes=1)}}
        as_of, delay, _, is_stale = market_service.freshness(quotes)
        # Gözlemden ölçülüyor, barın tarihinden değil: bir dakika önce
        # görülmüş bir fiyat eski DEĞİL.
        assert delay == market_service.PROVIDER_DELAY_FLOOR_MINUTES
        assert is_stale is False
        assert as_of > midnight

    def test_uses_the_oldest_observation_in_the_set(self):
        """A payload is only as current as its least current figure."""
        from datetime import timedelta

        quotes = {
            "A": {"received_at": NOW - timedelta(minutes=5)},
            "B": {"received_at": NOW - timedelta(minutes=45)},
        }
        as_of, delay, is_delayed, is_stale = market_service.freshness(quotes)
        assert as_of == NOW - timedelta(minutes=45)
        # Gecikme BESLEMENİN, gözlemin yaşı değil. İkisi bir dönem
        # toplanıyordu ve kapalı bir borsanın son kapanışı "1095 dakika
        # gecikmeli" diye raporlanıyordu.
        assert delay == market_service.PROVIDER_DELAY_FLOOR_MINUTES
        assert is_delayed is True
        # Kırk beş dakika henüz eski değil (eşik 60).
        assert is_stale is False

    def test_the_provider_floor_is_what_is_reported(self):
        """We cannot observe the exchange's true tick time, so the feed's own
        delay is declared rather than pretended away -- ve TEK BAŞINA
        bildiriliyor, gözlemin yaşı eklenmeden."""
        quotes = {"A": {"received_at": NOW}}
        _, delay, is_delayed, _ = market_service.freshness(quotes)
        assert delay == market_service.PROVIDER_DELAY_FLOOR_MINUTES
        assert is_delayed is True

    def test_an_old_observation_is_stale_rather_than_delayed(self):
        """`STALE_AFTER_MINUTES` bu ayrımı baştan beri adlandırıyordu
        ("beyond this, a quote is not delayed, it is stale") ve hiçbir yerde
        kullanılmıyordu.

        Ölçülen sonuç: kapalı bir borsanın son kapanışı on sekiz saat
        yaşlanınca kullanıcıya "1095 dakika gecikmeli" deniyordu."""
        from datetime import timedelta

        quotes = {"A": {"received_at": NOW - timedelta(hours=18)}}
        _, delay, _, is_stale = market_service.freshness(quotes)
        assert is_stale is True
        # Besleme on sekiz saat gecikmiyor; piyasa kapalı.
        assert delay == market_service.PROVIDER_DELAY_FLOOR_MINUTES

    @pytest.mark.parametrize("minutes,stale", [(59, False), (61, True)])
    def test_the_threshold_is_the_named_constant(self, minutes, stale):
        from datetime import timedelta

        quotes = {"A": {"received_at": NOW - timedelta(minutes=minutes)}}
        assert market_service.freshness(quotes)[3] is stale
        assert market_service.STALE_AFTER_MINUTES == 60

    def test_a_fresh_quote_is_still_reported_as_delayed(self):
        """Free-tier BIST data is delayed by design. Claiming otherwise would
        be false in the ordinary case, not the edge."""
        assert market_service.freshness({"A": {"received_at": NOW}})[2] is True

    def test_falls_back_to_the_bar_timestamp_when_unobserved(self):
        quotes = {"A": {"market_timestamp": NOW}}
        as_of, _, _, _ = market_service.freshness(quotes)
        assert as_of is not None

    def test_no_quotes_reports_delayed_rather_than_current(self):
        as_of, delay, is_delayed, is_stale = market_service.freshness({})
        assert as_of is None
        assert is_delayed is True
        # Hiç kotasyon yoksa gözlem de yok: bunu "taze" saymak, olmayan bir
        # fiyatı güncel ilan etmek olurdu.
        assert is_stale is True

    def test_naive_timestamp_is_treated_as_utc(self):
        quotes = {"A": {"received_at": NOW.replace(tzinfo=None)}}
        _, delay, _, _ = market_service.freshness(quotes)
        assert delay >= 0


class TestNewsStore:
    def test_empty_batch_makes_no_query(self):
        db = MagicMock(spec=Session)
        assert news_service.upsert_news(db, []) == (0, {}, [])
        assert db.execute.called is False

    def test_articles_are_deduplicated_on_content_hash(self):
        """Not on URL: the same wire story is republished under different
        links, and a feed that renumbers would re-import its whole history."""
        db = MagicMock(spec=Session)
        # `RETURNING` ile eklenen satırlar dönüyor: kaç tane olduğu değil,
        # HANGİLERİ. Bildirim yalnızca gerçekten eklenen haber için üretilmeli.
        db.execute.return_value.all.return_value = [("id-1", "a" * 64)]
        written, _, _fresh = news_service.upsert_news(
            db,
            [
                {
                    "content_hash": "a" * 64, "title": "Başlık", "source": "Dünya",
                    "published_at": NOW,
                }
            ],
        )
        assert written == 1
        statement = str(db.execute.call_args.args[0])
        assert "ON CONFLICT" in statement.upper()
        assert "content_hash" in statement

    def test_a_batch_that_inserted_nothing_reports_zero(self):
        """Hepsi zaten duruyorsa `RETURNING` boş döner -- ve bildirim de
        üretilmez, ki tekrar eden bir gürültü çıkmasın."""
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = []
        written, _, fresh = news_service.upsert_news(
            db, [{"content_hash": "b" * 64, "title": "t", "source": "s", "published_at": NOW}]
        )
        assert written == 0 and fresh == []

    def test_only_symbol_tagged_new_articles_reach_the_notifier(self, mocker):
        """Hiçbir hisseye bağlanmayan haber bildirilecek kimseyi
        göstermiyor; listeye hiç girmiyor."""
        db = MagicMock(spec=Session)
        mocker.patch.object(news_service, "_tradable_universe", return_value=[])
        db.execute.return_value.all.return_value = [("id-1", "c" * 64)]
        _written, _symbols, fresh = news_service.upsert_news(
            db, [{"content_hash": "c" * 64, "title": "Genel piyasa yorumu",
                  "source": "s", "published_at": NOW}]
        )
        assert fresh == []


class TestNewsSymbolResolution:
    """Haberi portföydeki hisseye bağlayan yer.

    Bu bağ olmadan "portföyünüzdeki hisseye dair haber" diye bir şey yok:
    `related_symbols` 1.540 haberin 1.540'ında boştu.
    """

    UNIVERSE = [
        SimpleNamespace(symbol="THYAO", name="Türk Hava Yolları A.O.", product_type="stock"),
        SimpleNamespace(symbol="ASELS", name="Aselsan Elektronik", product_type="stock"),
    ]

    def _db(self):
        db = MagicMock(spec=Session)
        # `RETURNING` eklenen satırları döndürüyor; bu sınıfın konusu
        # sembol çözümlemesi, dolayısıyla tek bir satır yeter.
        db.execute.return_value.all.return_value = [("id-1", "d" * 64)]
        db.query.return_value.filter.return_value.all.return_value = self.UNIVERSE
        return db

    def _stored(self, db):
        return db.execute.call_args.args[0].compile().params

    def test_a_company_named_in_the_headline_is_linked(self, mocker):
        db = self._db()
        news_service.upsert_news(db, [{
            "content_hash": "c" * 64, "title": "Türk Hava Yolları'ndan rekor",
            "source": "Dünya", "published_at": NOW,
        }])
        assert self._stored(db)["related_symbols_m0"] == ["THYAO"]

    def test_a_story_naming_no_company_is_linked_to_nothing(self):
        db = self._db()
        news_service.upsert_news(db, [{
            "content_hash": "d" * 64, "title": "Merkez Bankası faiz kararını açıkladı",
            "source": "AA", "published_at": NOW,
        }])
        assert self._stored(db)["related_symbols_m0"] == []

    def test_a_feed_supplied_ticker_is_kept_without_reading_the_text(self):
        """KAP bildirimleri ihraççısıyla birlikte gelir. Kesin bilgiyi
        metinden çıkarımla değiştirmek geriye gidiş olurdu."""
        db = self._db()
        news_service.upsert_news(db, [{
            "content_hash": "e" * 64, "title": "Türk Hava Yolları'ndan rekor",
            "source": "KAP", "published_at": NOW, "related_symbols": ["ASELS"],
        }])
        assert self._stored(db)["related_symbols_m0"] == ["ASELS"]

    def test_a_section_name_offered_as_a_ticker_is_dropped(self):
        """Türkçe finans beslemeleri yazıları `BORSA` ve `FINANS` bölümlerine
        koyuyor; ikisi de "3-6 harf" testini geçer ama enstrüman değildir.
        Evrende karşılığı olmayan etiket düşer ve metinden çözümleme devreye
        girer."""
        db = self._db()
        news_service.upsert_news(db, [{
            "content_hash": "f" * 64, "title": "Türk Hava Yolları'ndan rekor",
            "source": "Dünya", "published_at": NOW,
            "related_symbols": ["BORSA", "FINANS"],
        }])
        assert self._stored(db)["related_symbols_m0"] == ["THYAO"]

    def test_only_stocks_are_offered_to_the_matcher(self):
        """Bir haberin "USDTRY" ya da "XU100" ile ilişkilendirilmesi,
        kullanıcıya şirket haberi vaat edip endeks haberi göstermek olurdu."""
        db = self._db()
        news_service.upsert_news(db, [{
            "content_hash": "0" * 64, "title": "x", "source": "s", "published_at": NOW,
        }])
        filter_arg = str(db.query.return_value.filter.call_args.args[0])
        assert "product_type" in filter_arg


class TestProductLookups:
    def test_get_product_filters_by_symbol(self):
        db = MagicMock(spec=Session)
        expected = SimpleNamespace(symbol="TEST-THYAO", id="p-1")
        db.query.return_value.filter.return_value.first.return_value = expected
        assert market_service.get_product(db, "TEST-THYAO") is expected

    def test_list_products_skips_instruments_with_no_feed(self):
        """`data_symbol IS NULL` means "do not price this". Fetching it anyway
        would ask the provider for a symbol it has never heard of on every
        cycle."""
        db = MagicMock(spec=Session)
        chain = db.query.return_value.filter.return_value.filter.return_value
        chain.order_by.return_value.all.return_value = [SimpleNamespace(symbol="TEST-THYAO")]
        assert len(market_service.list_products(db)) == 1
        assert db.query.return_value.filter.return_value.filter.called

    def test_list_products_can_include_unpriced_ones(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        assert market_service.list_products(db, only_priced=False) == []


class TestLatestQuotes:
    def test_rows_are_keyed_by_symbol_with_floats(self):
        db = MagicMock(spec=Session)
        quote = SimpleNamespace(
            price=295.5, change_amount=4.5, change_percent=1.55,
            previous_close=291.0, volume=1000,
            market_timestamp=NOW, received_at=NOW, source="yfinance",
        )
        db.execute.return_value.all.return_value = [(quote, "TEST-THYAO", "TRY")]
        out = market_service.latest_quotes(db)
        assert out["TEST-THYAO"]["price"] == 295.5
        assert out["TEST-THYAO"]["currency"] == "TRY"

    def test_null_change_fields_stay_none(self):
        db = MagicMock(spec=Session)
        quote = SimpleNamespace(
            price=295.5, change_amount=None, change_percent=None,
            previous_close=None, volume=None, market_timestamp=NOW,
            received_at=NOW, source="yfinance",
        )
        db.execute.return_value.all.return_value = [(quote, "TEST-THYAO", "TRY")]
        out = market_service.latest_quotes(db)
        assert out["TEST-THYAO"]["change_amount"] is None

    def test_symbol_filter_is_applied(self):
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = []
        market_service.latest_quotes(db, ["USDTRY"])
        assert "IN " in str(db.execute.call_args.args[0]).upper()


class TestCandleCloses:
    def test_unknown_product_yields_no_series(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        assert market_service.candle_closes(db, "NOPE") == []

    def test_series_is_returned_oldest_first(self):
        """Return calculations walk forward in time; a reversed series would
        produce sign-flipped returns that still look plausible."""
        from datetime import timedelta

        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id="p-1")
        # Core select ile okunuyor: sadece iki sütun için ORM nesnesi kurmak,
        # sorgunun kendisinden yüz kat pahalıydı.
        db.execute.return_value.all.return_value = [
            (NOW, 300.0),
            (NOW - timedelta(days=1), 295.0),
        ]
        series = market_service.candle_closes(db, "TEST-THYAO")
        assert [price for _, price in series] == [295.0, 300.0]


class TestLatestNews:
    def test_orders_newest_first_and_applies_the_limit(self):
        """Ties on published_at are broken by id so pagination is stable;
        without it two articles stamped the same second can swap places
        between requests."""
        db = MagicMock(spec=Session)
        rows = [SimpleNamespace(id="n-2"), SimpleNamespace(id="n-1")]
        db.query.return_value.order_by.return_value.limit.return_value.all.return_value = rows
        assert news_service.latest_news(db, limit=5) == rows
        db.query.return_value.order_by.return_value.limit.assert_called_once_with(5)


class TestNewsIdHelper:
    def test_generated_ids_are_unique(self):
        assert news_service._new_id() != news_service._new_id()


class TestInstrumentFilters:
    """Each filter has to reach SQL. A silently dropped one turns "no
    matches" into a false statement about the market."""

    def _db(self):
        db = MagicMock(spec=Session)
        db.execute.return_value.all.return_value = []
        db.query.return_value.filter.return_value.first.return_value = None
        db.query.return_value.filter.return_value.limit.return_value.all.return_value = []
        return db

    @pytest.mark.parametrize(
        "filters,expected",
        [
            ({"market": "BIST"}, "market"),
            ({"product_type": "stock"}, "product_type"),
            ({"sector": "Industrials"}, "sector"),
            ({"min_pe": 5}, "pe_ratio"),
            ({"max_pb": 2}, "pb_ratio"),
        ],
    )
    def test_filter_reaches_the_query(self, filters, expected):
        db = self._db()
        market_service.list_instruments(db, filters=filters)
        assert expected in str(db.execute.call_args.args[0])

    def test_a_pb_filter_also_excludes_unknown_values(self):
        db = self._db()
        market_service.list_instruments(db, filters={"max_pb": 2})
        assert "IS NOT NULL" in str(db.execute.call_args.args[0]).upper()


class TestFundamentalsNameField:
    def test_the_company_name_survives_the_ingest_boundary(self):
        """Pydantic drops undeclared fields, so the ingestor sent `name` and
        the backfill never received it — 84 of 97 instruments stayed named
        after their ticker and "Aselsan" would not resolve."""
        from app.modules.market.schemas import FundamentalsIn

        parsed = FundamentalsIn(symbol="ASELS", name="ASELSAN Elektronik")
        assert parsed.name == "ASELSAN Elektronik"

    def test_a_missing_name_stays_none(self):
        from app.modules.market.schemas import FundamentalsIn

        assert FundamentalsIn(symbol="ASELS").name is None


class TestRefreshQuotes:
    """Sohbet için anlık fiyat tazeleme.

    Fiyatı backend çekmiyor: yfinance'a çıkan tek bileşen ingestor ve
    veritabanı kredensiyeli olmayan da o.
    """

    def test_nothing_to_do_without_symbols(self):
        assert market_module_service.refresh_quotes([]) is False
        assert market_module_service.refresh_quotes(["  "]) is False

    def test_an_unconfigured_install_simply_does_not_refresh(self, monkeypatch):
        """Tazeleme yoksa bu bir hata değil: fiyatlar toplu turdan gelir."""
        monkeypatch.delenv("INGESTOR_REFRESH_URL", raising=False)
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        assert market_module_service.refresh_quotes(["THYAO"]) is False

        monkeypatch.setenv("INGESTOR_REFRESH_URL", "http://ingestor:8200")
        monkeypatch.delenv("BACKEND_API_KEY", raising=False)
        assert market_module_service.refresh_quotes(["THYAO"]) is False

    def test_it_posts_the_symbols_and_reports_success(self, monkeypatch, mocker):
        monkeypatch.setenv("INGESTOR_REFRESH_URL", "http://ingestor:8200/")
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        post = mocker.patch.object(
            market_module_service.httpx, "post",
            return_value=SimpleNamespace(
                raise_for_status=lambda: None, json=lambda: {"refreshed": 1},
            ),
        )
        assert market_module_service.refresh_quotes(["thyao"]) is True
        assert post.call_args.kwargs["json"] == {"symbols": ["THYAO"]}
        assert post.call_args.args[0] == "http://ingestor:8200/refresh"

    def test_too_many_symbols_are_trimmed(self, monkeypatch, mocker):
        """Bu yolu toplu çekim için kullanmak, on beş dakikalık turun var olma
        sebebini ortadan kaldırırdı."""
        monkeypatch.setenv("INGESTOR_REFRESH_URL", "http://ingestor:8200")
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        post = mocker.patch.object(
            market_module_service.httpx, "post",
            return_value=SimpleNamespace(
                raise_for_status=lambda: None, json=lambda: {"refreshed": 0},
            ),
        )
        many = [f"S{i}" for i in range(market_module_service.REFRESH_MAX_SYMBOLS + 10)]
        market_module_service.refresh_quotes(many)
        sent = post.call_args.kwargs["json"]["symbols"]
        assert len(sent) == market_module_service.REFRESH_MAX_SYMBOLS

    def test_a_failure_is_swallowed_so_the_turn_still_answers(
        self, monkeypatch, mocker
    ):
        """Tazeleme denemesi başarısız diye sohbetin cevapsız kalması, eski
        fiyattan kötüdür."""
        monkeypatch.setenv("INGESTOR_REFRESH_URL", "http://ingestor:8200")
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        mocker.patch.object(
            market_module_service.httpx, "post",
            side_effect=RuntimeError("ingestor down"),
        )
        assert market_module_service.refresh_quotes(["THYAO"]) is False
