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
