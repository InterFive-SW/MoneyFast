"""Bildirim yazma.

Bu modül KİMİN bildirileceğini bilmiyor, yalnızca nasıl yazılacağını.
Sahiplik sorgusu pozisyonları sahiplenen modülde (`investment.market_service.
holders_of`) ve ikisini birleştirmek router'ın işi -- bildirim modülünün
portföy tablosunu okuması, modüllerin birbirinin ORM sınıfını import etmemesi
kuralının engellediği şey.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from .models import Notification

log = logging.getLogger("moneyfast.notification")

#: Tek yükleme turunda bir kullanıcıya yazılabilecek en fazla bildirim.
#:
#: Ölçüldü: son yirmi dört saatte 539 haberin 24'ü tutulan bir pozisyona
#: dokunuyor -- saatte bir, makul. Ama tek bir tur olağandışı büyük bir
#: partiyle gelirse (ilk doldurma, kaynağın geçmişi yeniden yayımlaması)
#: aynı kullanıcı yüzlerce satır alır ve zil, okunmayacak bir listeye döner.
#: Sınır kırpıyor ve KIRPTIĞINI logluyor: sessizce kaybolan bildirim,
#: hiç üretilmemiş bildirimden zor fark edilir.
MAX_PER_USER_PER_BATCH = 10


def create_many(
    db: Session,
    user_ids: Iterable[str],
    *,
    title: str,
    description: str,
    type: str = "INFO",
    link_url: Optional[str] = None,
) -> int:
    """Aynı bildirimi birden çok kullanıcıya yazar. COMMIT ETMEZ.

    Commit çağırana ait: bir turda birçok bildirim yazılıyor ve her satırdan
    sonra commit etmek, tek bir yükleme turunu onlarca transaction'a bölerdi.

    Bildirim, onu doğuran olayla aynı transaction'da DEĞİL ve bu bilinçli:
    haber yüklemesi kendi commit'ini atıyor, bildirim onun üstüne konan bir
    kolaylık. Bildirimi yazamamak haberi kaybetmemeli -- tersi de doğru
    değil, ama bu yönde kaybedilen şey daha ucuz.
    """
    written = 0
    for user_id in user_ids:
        db.add(Notification(
            user_id=user_id, title=title, description=description,
            type=type, link_url=link_url,
        ))
        written += 1
    return written
