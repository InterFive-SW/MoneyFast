"""Görüntülenen saat.

Ölçülen hata: saat 10:00'da verilen bir emrin onay e-postasında **07:00**
yazıyordu. `email.py` ve `pdf_generator.py` tz-aware UTC bir `datetime` alıp
çevirmeden `strftime`'lıyordu, yani kullanıcı işlemini yapmadığı bir saatte
yapılmış görüyordu.

Saklama UTC KALIYOR: bu modül yalnızca kullanıcıya gösterilen metni
üretiyor.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core import timezone as tz


class TestToLocal:
    def test_an_aware_utc_moment_becomes_istanbul_wall_time(self):
        moment = datetime(2026, 9, 5, 7, 0, tzinfo=timezone.utc)
        assert tz.to_local(moment).hour == 10

    def test_a_naive_moment_is_read_as_utc(self):
        """Bu depoda her şey UTC yazılıyor; naive bir damga dilimi düşmüş bir
        UTC damgasıdır. Sunucunun yerel dilimini varsaymak, konteyner
        dilimine göre değişen bir sonuç üretirdi."""
        assert tz.to_local(datetime(2026, 9, 5, 7, 0)).hour == 10

    def test_nothing_stays_nothing(self):
        assert tz.to_local(None) is None


class TestFormatLocal:
    def test_the_default_format_is_day_first(self):
        moment = datetime(2026, 9, 5, 7, 0, tzinfo=timezone.utc)
        assert tz.format_local(moment) == "05.09.2026 10:00"

    def test_a_custom_format_is_honoured(self):
        moment = datetime(2026, 9, 5, 7, 0, tzinfo=timezone.utc)
        assert tz.format_local(moment, "%H:%M") == "10:00"

    def test_a_missing_moment_is_an_empty_string_not_a_word(self):
        """Çağıranların hepsi bu metni bir cümlenin içine gömüyor; orada ne
        yazılacağına çağıran karar vermeli."""
        assert tz.format_local(None) == ""


def test_now_is_reported_in_istanbul():
    assert now_offset() == tz.now_local().utcoffset()


def now_offset():
    return datetime.now(tz.ISTANBUL).utcoffset()
