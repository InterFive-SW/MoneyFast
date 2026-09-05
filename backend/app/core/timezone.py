"""Görüntülenen saat — tek yer, tek dilim.

`frontend/src/lib/datetime.ts`'in backend karşılığı ve aynı gerekçeyle var.

**Saklama UTC kalıyor.** Sütunların hepsi `DateTime(timezone=True)` ve her
`datetime.now(timezone.utc)` olduğu gibi duruyor; bu dosya yalnızca
KULLANICIYA GÖSTERİLEN metni üretiyor. Konteynerin `TZ`'sini değiştirmek
yanlış çözüm olurdu: saklanan değerin anlamını ortama bağlar, ve `ingestor`
piyasa saatlerini zaten açık `ZoneInfo` ile hesaplıyor.

Neden gerekiyordu: `email.py` ve `pdf_generator.py` tz-aware UTC bir
`datetime` alıp ÇEVİRMEDEN `strftime`'lıyordu. Ölçülen sonuç, saat 10:00'da
verilen bir emrin onay e-postasında **07:00** yazmasıydı -- kullanıcı
işlemini yapmadığı bir saatte yapılmış görüyordu.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

#: Uygulamanın saati. Kullanıcı Türkiye'de ve piyasa Türkiye'de.
ISTANBUL = ZoneInfo("Europe/Istanbul")


def to_local(moment: Optional[datetime]) -> Optional[datetime]:
    """Bir anı Istanbul duvar saatine çevirir.

    Naive bir değer UTC sayılıyor: bu depoda her şey UTC olarak yazılıyor ve
    naive bir damga, dilimi düşmüş bir UTC damgasıdır. Sunucunun yerel
    dilimini varsaymak, konteyner dilimine göre değişen bir sonuç üretirdi.
    """
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(ISTANBUL)


def format_local(moment: Optional[datetime], fmt: str = "%d.%m.%Y %H:%M") -> str:
    """Istanbul saatiyle biçimlendirilmiş metin; değer yoksa boş dize.

    Boş dize döndürüyor, "bilinmiyor" YAZMIYOR: çağıranların hepsi bu metni
    bir cümlenin içine gömüyor ve orada ne yazılacağına çağıran karar
    vermeli.
    """
    local = to_local(moment)
    return local.strftime(fmt) if local is not None else ""


def now_local() -> datetime:
    """Şimdi, Istanbul duvar saatiyle."""
    return datetime.now(timezone.utc).astimezone(ISTANBUL)
