"""Fon listesi ve getirileri.

`Fonlar` ekranı `MOCK_FUNDS` üzerinden çiziliyordu. Buradaki iddiaların en
önemlisi neyin YOK olduğu: TEFAS API'si yönetim ücreti, stopaj, risk değeri
ve hisse bazında dağılım DÖNDÜRMÜYOR (HAR kaydındaki 85 alanın hepsi
tarandı) ve o alanlar için sütun açılmadı. Boş bir sütun, bir gün
dolacakmış gibi duran bir söz olurdu.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.market import funds as funds_service
from app.modules.market.schemas import FundOut


def price(day: str, value: float):
    return SimpleNamespace(as_of=date.fromisoformat(day), price=value)


class TestReturns:
    def test_a_window_is_measured_against_the_first_observation_after_it(self):
        """NAV yalnızca iş günlerinde yayımlanıyor; tam o günü aramak hafta
        sonuna denk gelen her pencereyi ölçülemez yapardı."""
        series = [price("2026-08-06", 100.0), price("2026-09-05", 110.0)]
        assert funds_service.returns_for(series)["monthly"] == 10.0

    def test_an_unmeasurable_window_is_null_not_zero(self):
        """`null` "bu fonun o kadar geçmişi yok", sıfır ise "o dönemde hiç
        kazandırmadı" -- karşıt iddialar."""
        series = [price("2026-09-04", 100.0), price("2026-09-05", 101.0)]
        out = funds_service.returns_for(series)
        assert out["daily"] == 1.0
        assert out["fiveYear"] is None
        assert out["yearly"] is None

    def test_an_empty_series_measures_nothing(self):
        assert set(funds_service.returns_for([]).values()) == {None}
        assert set(funds_service.returns_for([])) == set(funds_service.RETURN_WINDOWS)

    def test_a_single_observation_measures_nothing(self):
        """Referans en son gözlemin kendisiyse pencere ölçülemiyor."""
        assert set(funds_service.returns_for([price("2026-09-05", 100.0)]).values()) == {None}

    def test_a_zero_reference_price_is_not_divided_by(self):
        series = [price("2026-08-06", 0.0), price("2026-09-05", 110.0)]
        assert funds_service.returns_for(series)["monthly"] is None

    def test_a_short_series_does_not_claim_a_long_window(self):
        """İki günlük bir seri "yıllık getiri %1" diyordu: en yakın gözlem
        olarak dünü alıp bir yıllık pencereye yazıyordu. Bir günün
        getirisini bir yılın getirisi diye sunmak, yanlış bir sayıdan daha
        kötü -- ölçek hatası."""
        series = [price("2026-09-04", 100.0), price("2026-09-05", 101.0)]
        out = funds_service.returns_for(series)
        assert out["daily"] == 1.0
        assert out["monthly"] is None
        assert out["threeMonth"] is None
        assert out["yearly"] is None

    def test_a_loss_is_negative(self):
        series = [price("2026-08-06", 100.0), price("2026-09-05", 90.0)]
        assert funds_service.returns_for(series)["monthly"] == -10.0


class TestSchemaOmissions:
    @pytest.mark.parametrize("absent", [
        "managementFee", "withholdingTax", "riskValue", "holdings", "netCashFlow",
    ])
    def test_fields_tefas_does_not_return_have_no_column(self, absent):
        """Mock'ta vardı, TEFAS'ta yok. `null` taşımak, bir gün dolacakmış
        gibi duran bir söz olurdu."""
        assert absent not in FundOut.model_fields

    def test_the_price_day_is_a_date_not_a_timestamp(self):
        """Fon fiyatı GÜNLÜKTÜR; zaman damgası taşımak olmayan bir anlık
        değeri varmış gibi gösterirdi."""
        assert FundOut.model_fields["asOf"].annotation.__args__[0] is date


class TestUpsert:
    """Kısmi güncelleme.

    `INSERT ... ON CONFLICT DO UPDATE` burada çalışmıyor: Postgres önerilen
    satırın NOT NULL kısıtlarını çatışmayı çözmeden ÖNCE denetliyor.
    ÖLÇÜLDÜ -- şemsiye türü güncellemesi satır zaten dururken bile
    `null value in column "title"` ile düştü.
    """

    def _db(self, rowcount=1):
        db = MagicMock()
        db.execute.return_value = SimpleNamespace(rowcount=rowcount)
        return db

    def test_an_existing_row_is_updated_not_re_inserted(self):
        db = self._db(rowcount=1)
        assert funds_service.upsert_funds(db, [{"code": "HAI", "umbrella": "ALTIN"}]) == 1
        # Tek çağrı: UPDATE. İkinci bir INSERT denemesi olsaydı NOT NULL
        # kısıtı yine patlardı.
        assert db.execute.call_count == 1

    def test_a_new_row_needs_a_title(self):
        """Adsız bir fon eklemek, listede boş bir satır üretirdi."""
        db = self._db(rowcount=0)
        assert funds_service.upsert_funds(db, [{"code": "YENI", "umbrella": "ALTIN"}]) == 0

    def test_a_new_row_with_a_title_is_inserted(self):
        db = self._db(rowcount=0)
        assert funds_service.upsert_funds(
            db, [{"code": "YENI", "title": "YENİ FON"}]) == 1
        assert db.execute.call_count == 2

    def test_a_row_without_a_code_is_skipped(self):
        db = self._db()
        assert funds_service.upsert_funds(db, [{"title": "AD"}]) == 0
        assert db.execute.call_count == 0

    def test_a_row_with_nothing_to_write_is_skipped(self):
        """Yalnızca kod taşıyan satır bir güncelleme değil."""
        db = self._db()
        assert funds_service.upsert_funds(db, [{"code": "AAL"}]) == 0
        assert db.execute.call_count == 0

    def test_null_values_never_overwrite_what_is_there(self):
        """Evren turu şemsiye türünü taşımıyor, günlük tur kurucuyu taşımıyor.
        Her turun diğerinin alanlarını NULL'la ezmesi, iki turu birbirinin
        işini bozar hâle getirirdi."""
        db = self._db()
        funds_service.upsert_funds(db, [{"code": "AAL", "title": "AD", "founder": None}])
        written = db.execute.call_args[0][0].compile().params
        assert "founder" not in written or written.get("founder") is not None


class TestCandles:
    """Fon günde TEK fiyat yayımlıyor.

    Günlük bir mumun açılış/yüksek/düşük/kapanışı aynı sayı olurdu -- yani
    mum değil, yassı bir çizgi. Gerçek bir mum ancak birkaç gün KOVALANARAK
    çıkıyor.
    """

    def _db(self, series):
        db = MagicMock()
        db.execute.return_value.scalars.return_value = series
        return db

    def test_a_week_becomes_one_candle_with_real_extremes(self, mocker):
        series = [
            price("2026-08-31", 10.0),  # pazartesi
            price("2026-09-01", 12.0),
            price("2026-09-02", 9.0),
            price("2026-09-03", 11.0),
        ]
        mocker.patch.object(funds_service, "price_series", return_value=series)
        out = funds_service.candles(MagicMock(), "AAL", "3A")
        assert len(out) == 1
        assert out[0]["open"] == 10.0   # kovanın ilk NAV'ı
        assert out[0]["high"] == 12.0
        assert out[0]["low"] == 9.0
        assert out[0]["close"] == 11.0  # kovanın son NAV'ı

    def test_two_weeks_become_two_candles(self, mocker):
        series = [price("2026-08-31", 10.0), price("2026-09-07", 20.0)]
        mocker.patch.object(funds_service, "price_series", return_value=series)
        assert len(funds_service.candles(MagicMock(), "AAL", "3A")) == 2

    def test_a_long_range_buckets_by_month(self, mocker):
        """Bir yılı haftalık kovalarla çizmek 52 çubuk demek; aylık kova
        okunabilir kalıyor."""
        series = [
            price("2026-07-01", 10.0), price("2026-07-20", 11.0),
            price("2026-08-05", 12.0),
        ]
        mocker.patch.object(funds_service, "price_series", return_value=series)
        out = funds_service.candles(MagicMock(), "AAL", "1Y")
        assert len(out) == 2
        assert out[0]["high"] == 11.0

    def test_candles_are_ordered_oldest_first(self, mocker):
        series = [price("2026-07-01", 10.0), price("2026-08-05", 12.0)]
        mocker.patch.object(funds_service, "price_series", return_value=series)
        out = funds_service.candles(MagicMock(), "AAL", "1Y")
        assert [c["date"] for c in out] == sorted(c["date"] for c in out)

    def test_rows_outside_the_window_are_excluded(self, mocker):
        """Pencere SON gözlemden geriye sayılıyor, bugünden değil: hafta
        sonu ya da tatil, bir fonun bütün serisini pencere dışına itmemeli."""
        series = [price("2020-01-01", 1.0), price("2026-09-04", 12.0)]
        mocker.patch.object(funds_service, "price_series", return_value=series)
        assert len(funds_service.candles(MagicMock(), "AAL", "1A")) == 1

    def test_an_empty_series_yields_no_candles(self, mocker):
        mocker.patch.object(funds_service, "price_series", return_value=[])
        assert funds_service.candles(MagicMock(), "AAL", "3A") == []

    def test_an_unknown_window_falls_back_rather_than_raising(self, mocker):
        mocker.patch.object(
            funds_service, "price_series", return_value=[price("2026-09-04", 1.0)],
        )
        assert funds_service.candles(MagicMock(), "AAL", "42Y") != []

    def test_no_volume_is_reported(self, mocker):
        """Bir fonun günlük işlem hacmi TEFAS'ta yayımlanmıyor ve sıfır
        yazmak "hiç kimse almadı" demek olurdu."""
        mocker.patch.object(
            funds_service, "price_series", return_value=[price("2026-09-04", 1.0)],
        )
        assert "volume" not in funds_service.candles(MagicMock(), "AAL", "3A")[0]

    def test_the_monday_of_a_week_keys_the_bucket(self):
        from datetime import date as _date

        assert funds_service._bucket_key(_date(2026, 9, 4), "week") == _date(2026, 8, 31)
        assert funds_service._bucket_key(_date(2026, 9, 4), "month") == _date(2026, 9, 1)


class TestCoverage:
    def test_a_fund_with_a_series_but_no_rank_is_listed_separately(self, mocker):
        """Kategori sırası fiyat serisiyle aynı yanıtta geliyor, ama seriyi
        ölçüler eklenmeden önce çekilmiş fonlarda sıra boş kaldı. Onları
        ayrıca listelemek, seriyi silip yeniden çekmekten ucuz."""
        db = MagicMock()
        db.execute.return_value.scalars.return_value.all.side_effect = [
            ["AAL", "AAS"],   # aktif fonlar
            [],               # şemsiyesi eksik
            ["AAL"],          # fiyatı olan
            ["AAL", "AAS"],   # sırası eksik
        ]
        out = funds_service.coverage(db)
        assert out["missing_prices"] == ["AAS"]
        # AAS'ın serisi zaten yok; iki kez istenmemeli.
        assert out["missing_category"] == ["AAL"]


class TestTradableBridge:
    """Fonun enstrüman evrenindeki karşılığı.

    Emirler, pozisyonlar, portföy değerlemesi ve risk yollarının HEPSİ
    `investment.investment_products` üzerinden geçiyor; fonlar ayrı bir
    tabloda durduğu sürece "fon al" diye bir yol yoktu. Köprü TEK TEK
    kuruluyor: 2.602 fonu evrene yazmak, Piyasalar ekranını kimsenin
    aramadığı fon kodlarıyla doldururdu.
    """

    def _db(self, existing=None, fund=None):
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = existing
        db.get.return_value = fund
        return db

    def test_a_traded_fund_is_written_into_the_universe(self, mocker):
        fund = SimpleNamespace(code="AFA", title="ATA PORTFÖY", active=True)
        db = self._db(fund=fund)
        mocker.patch.object(funds_service, "sync_quotes", return_value=1)

        product = funds_service.ensure_tradable(db, "afa")
        assert product.symbol == "AFA"
        # İki `flush`: oturum `autoflush=False` ve kotasyon aynı istek
        # içinde bir SELECT'e görünmeli. Ölçüldü -- fonun ilk emri "Fiyat
        # bilgisi bulunamayan enstrüman" ile reddediliyordu.
        assert db.flush.call_count == 2
        assert product.product_type == funds_service.FUND_PRODUCT_TYPE
        # `data_symbol` BOŞ: yfinance bir TEFAS kodunu fiyatlayamaz ve boş
        # bırakmak "bunu fiyatlamaya çalışma" demek.
        assert product.data_symbol is None
        db.add.assert_called_once_with(product)

    def test_an_existing_instrument_is_never_overwritten(self):
        """Aynı kodu taşıyan bir hisse buradan sessizce ezilmemeli."""
        existing = SimpleNamespace(symbol="AFA")
        db = self._db(existing=existing)
        assert funds_service.ensure_tradable(db, "AFA") is existing
        db.add.assert_not_called()

    @pytest.mark.parametrize("fund", [
        None,
        SimpleNamespace(code="AFA", title="X", active=False),
    ])
    def test_an_unknown_or_closed_fund_is_not_bridged(self, fund):
        db = self._db(fund=fund)
        assert funds_service.ensure_tradable(db, "AFA") is None
        db.add.assert_not_called()

    def test_an_empty_code_is_not_bridged(self):
        db = self._db()
        assert funds_service.ensure_tradable(db, "  ") is None
        db.execute.assert_not_called()


class TestFundQuotes:
    """Tek fiyat kuralı: portföy değeri ve bekleyen fon emirleri
    `market_quotes`tan okuyor, `market.funds`tan değil."""

    def _db(self, products, funds, series=()):
        db = MagicMock()
        results = [
            SimpleNamespace(all=lambda rows=products: rows),
            SimpleNamespace(scalars=lambda rows=funds: rows),
        ]
        db.execute.side_effect = results
        return db

    def test_a_fund_with_two_days_reports_a_change(self, mocker):
        db = self._db(
            products=[("prod-1", "AFA")],
            funds=[SimpleNamespace(code="AFA", price=12.5, as_of=date(2026, 9, 4))],
        )
        mocker.patch.object(
            funds_service, "price_series",
            return_value=[price("2026-09-03", 12.0), price("2026-09-04", 12.5)],
        )
        assert funds_service.sync_quotes(db) == 1
        quote = db.merge.call_args[0][0]
        assert float(quote.price) == 12.5
        assert float(quote.previous_close) == 12.0
        assert quote.change_percent == pytest.approx(4.1667, abs=1e-3)
        assert quote.source == funds_service.FUND_QUOTE_SOURCE

    def test_a_single_day_reports_an_unknown_change_not_zero(self, mocker):
        """Sıfır yazmak, "gün içinde değişmedi" iddiası olurdu."""
        db = self._db(
            products=[("prod-1", "AFA")],
            funds=[SimpleNamespace(code="AFA", price=12.5, as_of=date(2026, 9, 4))],
        )
        mocker.patch.object(
            funds_service, "price_series", return_value=[price("2026-09-04", 12.5)]
        )
        funds_service.sync_quotes(db)
        quote = db.merge.call_args[0][0]
        assert quote.change_percent is None
        assert quote.change_amount is None

    @pytest.mark.parametrize("fund", [
        None,
        SimpleNamespace(code="AFA", price=None, as_of=date(2026, 9, 4)),
        SimpleNamespace(code="AFA", price=12.5, as_of=None),
    ])
    def test_a_fund_without_a_usable_nav_is_skipped(self, fund, mocker):
        db = self._db(
            products=[("prod-1", "AFA")],
            funds=[fund] if fund is not None else [],
        )
        mocker.patch.object(funds_service, "price_series", return_value=[])
        assert funds_service.sync_quotes(db) == 0
        db.merge.assert_not_called()

    def test_no_bridged_funds_means_no_work(self):
        db = MagicMock()
        db.execute.return_value.all.return_value = []
        assert funds_service.sync_quotes(db) == 0
        db.merge.assert_not_called()

    def test_a_code_filter_narrows_the_scan(self, mocker):
        """Yeni köprülenen tek fonun kotasyonu yazılırken bütün evren
        taranmamalı."""
        db = self._db(
            products=[("prod-1", "AFA")],
            funds=[SimpleNamespace(code="AFA", price=12.5, as_of=date(2026, 9, 4))],
        )
        mocker.patch.object(
            funds_service, "price_series", return_value=[price("2026-09-04", 12.5)]
        )
        assert funds_service.sync_quotes(db, ["afa"]) == 1


class TestUpsertPrices:
    """NAV serisi. `DO NOTHING` DEĞİL: TEFAS bir günün fiyatını sonradan
    düzeltebiliyor ve ilk yazılanı korumak, düzeltilmiş bir fiyatı
    reddetmek olurdu."""

    def test_a_corrected_price_overwrites_the_first_one(self):
        db = MagicMock()
        assert funds_service.upsert_prices(
            db, [{"code": "afa", "as_of": date(2026, 9, 4), "price": 12.5}]
        ) == 1
        assert "DO UPDATE" in str(db.execute.call_args[0][0])

    @pytest.mark.parametrize("row", [
        {"as_of": date(2026, 9, 4), "price": 12.5},
        {"code": "AFA", "price": 12.5},
        {"code": "AFA", "as_of": date(2026, 9, 4)},
    ])
    def test_an_incomplete_row_is_skipped(self, row):
        """Günü ya da fiyatı olmayan bir NAV, seride bir delik değil bir
        yalan olurdu."""
        db = MagicMock()
        assert funds_service.upsert_prices(db, [row]) == 0
        db.execute.assert_not_called()


class TestListingAndFacets:
    def test_every_filter_narrows_the_query(self):
        db = MagicMock()
        funds_service.list_funds(
            db, founder="ATA", umbrella="ALTIN", fund_type="yat",
            search="ata", limit=5, offset=10,
        )
        compiled = str(db.execute.call_args[0][0])
        for column in ("founder", "umbrella", "fund_type", "title", "code"):
            assert column in compiled

    def test_the_default_order_is_by_size_with_unknowns_last(self):
        """Alfabetik sıralamak, ekranın ilk ekranını kimsenin aramadığı
        fonlarla doldururdu. Büyüklüğü bilinmeyen fon SONA gidiyor, sıfır
        sayılmıyor."""
        db = MagicMock()
        funds_service.list_funds(db)
        compiled = str(db.execute.call_args[0][0]).upper()
        assert "ORDER BY" in compiled
        assert "NULLS LAST" in compiled

    def test_the_dropdowns_are_read_from_the_data(self):
        """Elle yazılmış bir liste, TEFAS yeni bir kurucu eklediğinde
        sessizce eksik kalırdı."""
        db = MagicMock()
        db.execute.return_value.scalars.side_effect = [["ATA"], ["ALTIN"]]
        assert funds_service.facets(db) == {
            "founders": ["ATA"], "umbrellas": ["ALTIN"],
        }


class TestPriceSeries:
    def test_the_series_comes_back_oldest_first(self):
        """Sorgu en yeniden alıyor (limit son N günü kessin diye), grafik ise
        eskiden yeniye çiziyor."""
        db = MagicMock()
        db.execute.return_value.scalars.return_value = [
            price("2026-09-04", 12.5), price("2026-09-01", 12.0),
        ]
        rows = funds_service.price_series(db, " afa ")
        assert [row.as_of.isoformat() for row in rows] == ["2026-09-01", "2026-09-04"]
