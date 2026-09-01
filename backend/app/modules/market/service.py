"""News storage and retrieval for the dashboard feed."""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Sequence

import httpx

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import NewsItem

log = logging.getLogger("moneyfast.market")


def upsert_news(db: Session, items: list[dict[str, Any]]) -> int:
    """Store articles, ignoring ones already held.

    Deduplicated on content_hash rather than URL: the same wire story is
    republished under different URLs, and a feed that renumbers its links
    would otherwise re-import its whole history every poll.
    """
    if not items:
        return 0

    payload = [
        {
            "id": item.get("id") or _new_id(),
            "content_hash": item["content_hash"],
            "title": item["title"],
            "summary": item.get("summary"),
            "source": item["source"],
            "url": item.get("url"),
            "language": item.get("language", "tr"),
            "related_symbols": item.get("related_symbols") or [],
            "published_at": item["published_at"],
            "ingested_at": datetime.now(timezone.utc),
        }
        for item in items
    ]
    statement = insert(NewsItem).values(payload).on_conflict_do_nothing(
        index_elements=["content_hash"]
    )
    result = db.execute(statement)
    db.commit()
    return result.rowcount or 0


def news_coverage(db: Session) -> dict[str, dict]:
    """Kaynak başına: kaç haber var, en yenisi ne zaman, en yüksek numara.

    `candle_coverage` ile aynı soru, haberler için. Ama bir fark var:
    KAP bildirim numarası MONOTON artıyor, dolayısıyla "elimizdeki en yüksek
    numara" bir tarihten hem daha ucuz hem daha kesin bir su seviyesi.

    Numara için ayrı bir sütun YOK ve gerekmiyor: kalıcı bağlantının kendisi
    numarayı taşıyor (`/tr/Bildirim/1655982`) ve o bağlantı atıf için zaten
    saklanıyor.

    **Bu bir su seviyesi, tamlık kanıtı değil.** Yarıda kesilmiş bir tur,
    en yüksek numaranın ALTINDA boşluk bırakır; onu `known-hashes` yakalar.
    """
    rows = db.execute(
        text(
            """
            SELECT source,
                   count(*)                    AS items,
                   max(published_at)           AS last,
                   max(CASE WHEN url ~ '/Bildirim/[0-9]+$'
                            THEN substring(url from '/Bildirim/([0-9]+)$')::bigint
                       END)                    AS last_index
            FROM market.news_items
            GROUP BY source
            """
        )
    ).all()
    return {
        row.source: {
            "items": row.items,
            # `~` koruması taşıyıcı: onsuz `::bigint` dönüşümü RSS
            # bağlantılarını da görür ve uç nokta 500 döner.
            "last": row.last.date().isoformat() if row.last else None,
            "last_index": int(row.last_index) if row.last_index is not None else None,
        }
        for row in rows
    }


#: Bir istekte sorulabilecek en fazla hash. Sınırsız bir liste, indeksli
#: sorguyu tablo taramasına çevirmenin en kolay yolu olurdu.
MAX_HASH_QUERY = 5_000


def known_hashes(db: Session, hashes: Sequence[str]) -> list[str]:
    """Verilen hash'lerden hangileri zaten kayıtlı.

    `ingestor`'ın gövde indirmeden ÖNCE sorduğu soru. KAP bildiriminin
    tekilleştirme anahtarı bildirim numarasından türetiliyor, yani listeleme
    yanıtından hesaplanabiliyor; dolayısıyla hangi bildirimin gövdesini
    çekmeye değeceği, hiçbir gövde indirilmeden bilinebiliyor.

    Bu olmadan altı aylık tarama yeniden başlatılabilir olmazdı: her açılış
    sıfırdan başlar ve arşiv hiç tamamlanmazdı.
    """
    if not hashes:
        return []
    rows = (
        db.query(NewsItem.content_hash)
        .filter(NewsItem.content_hash.in_(list(hashes)))
        .all()
    )
    return [row[0] for row in rows]


def latest_news(db: Session, limit: int = 20) -> list[NewsItem]:
    return (
        db.query(NewsItem)
        .order_by(NewsItem.published_at.desc(), NewsItem.id.desc())
        .limit(limit)
        .all()
    )


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())


# ── Anlık fiyat tazeleme ─────────────────────────────────────────────────────

#: Ingestor'dan cevap beklenecek azami süre. Kısa bilerek: sohbet turunu
#: bekletmektense on beş dakikalık fiyatla cevap vermek yeğ. Tazeleme bir
#: iyileştirme, bir önkoşul değil.
REFRESH_TIMEOUT_SECONDS = 6.0

#: Tek turda tazelenecek azami sembol; ingestor tarafındaki sınırla aynı.
REFRESH_MAX_SYMBOLS = 25


def refresh_quotes(symbols: Sequence[str]) -> bool:
    """Adı geçen sembolleri ingestor'a şimdi çektirir.

    Hisse fiyatları on beş dakikada bir tazeleniyor; ekranlar için yeterli,
    sohbet için değil. "THYAO kaç TL" sorusuna on beş dakika önceki fiyatla
    cevap vermek, kullanıcının işlem kararını verdiği anda yanlış sayı
    göstermek olurdu.

    **Best-effort.** Ingestor kapalıysa, yavaşsa ya da sağlayıcı cevap
    vermiyorsa sessizce vazgeçilir ve elde olan fiyatla devam edilir: tazeleme
    denemesi başarısız diye sohbetin cevapsız kalması, eski fiyattan kötüdür.

    Döndürdüğü değer, tazelemenin GERÇEKLEŞTİĞİ anlamına gelir; çağıran buna
    bakarak yeniden okuyup okumayacağına karar verir.
    """
    wanted = [str(s).strip().upper() for s in (symbols or []) if str(s).strip()]
    if not wanted:
        return False

    base = os.getenv("INGESTOR_REFRESH_URL")
    token = os.getenv("BACKEND_API_KEY")
    if not base or not token:
        # Yapılandırılmamış bir kurulumda bu bir hata değil: tazeleme yok,
        # fiyatlar toplu turdan gelir.
        return False

    try:
        response = httpx.post(
            f"{base.rstrip('/')}/refresh",
            json={"symbols": wanted[:REFRESH_MAX_SYMBOLS]},
            headers={"Authorization": f"Bearer {token}"},
            timeout=REFRESH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except Exception as exc:
        log.info("quote refresh skipped (%s): %s", type(exc).__name__, exc)
        return False

    written = (response.json() or {}).get("refreshed", 0)
    log.info("refreshed %s quote(s) for %s", written, ", ".join(wanted[:5]))
    return bool(written)
