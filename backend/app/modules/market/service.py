"""News storage and retrieval for the dashboard feed."""

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Sequence

import httpx

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.investment.models import InvestmentProduct

from . import symbol_match
from .models import NewsItem

log = logging.getLogger("moneyfast.market")

#: Haberde KODUYLA aranan piyasalar. Beslemeler Türkçe ve Türkçe bir haber
#: bir ABD şirketini kodyla değil adıyla anar; ABD kodları ise Türkçe
#: kısaltmalarla çakışıyor. Ölçüldü: 1.542 haberde ABD kodu 7 kez eşleşti,
#: yedisi de yanlıştı. Ad eşleşmesi tüm evrende çalışmaya devam ediyor.
LOCAL_TICKER_MARKETS = {"BIST"}


def upsert_news(db: Session, items: list[dict[str, Any]]) -> int:
    """Store articles, ignoring ones already held.

    Deduplicated on content_hash rather than URL: the same wire story is
    republished under different URLs, and a feed that renumbers its links
    would otherwise re-import its whole history every poll.
    """
    if not items:
        return 0

    universe = _tradable_universe(db)
    payload = [
        {
            "id": item.get("id") or _new_id(),
            "content_hash": item["content_hash"],
            "title": item["title"],
            "summary": item.get("summary"),
            "source": item["source"],
            "url": item.get("url"),
            "language": item.get("language", "tr"),
            "related_symbols": _symbols_for(item, universe),
            "published_at": item["published_at"],
            "ingested_at": datetime.now(timezone.utc),
        }
        for item in items
    ]
    matched = sum(1 for row in payload if row["related_symbols"])
    if matched:
        log.info("resolved symbols for %d of %d articles", matched, len(payload))

    statement = insert(NewsItem).values(payload).on_conflict_do_nothing(
        index_elements=["content_hash"]
    )
    result = db.execute(statement)
    db.commit()
    return result.rowcount or 0


def _tradable_universe(db: Session) -> list[InvestmentProduct]:
    """Haberin bağlanabileceği enstrümanlar.

    Yalnızca hisseler: bir haberin "USDTRY" ya da "XU100" ile ilişkilendirilmesi
    kullanıcıya bir şirket haberi vaat edip endeks haberi göstermek olurdu.
    """
    return (
        db.query(InvestmentProduct)
        .filter(InvestmentProduct.product_type == "stock")
        .all()
    )


def _symbols_for(item: dict[str, Any], universe: list[InvestmentProduct]) -> list[str]:
    """Haberin bahsettiği semboller.

    Kaynak kendi etiketini verdiyse ona dokunulmaz: KAP bildirimleri
    ihraççıyla birlikte gelir ve metinden çıkarım yapmak, kesin bilgiyi
    tahminle değiştirmek olurdu. Yalnızca etiketsiz gelen haberler için
    metinden çözümleme yapılır.
    """
    known = {row.symbol.upper() for row in universe}
    # Beslemenin verdiği etiketler ADAY, sonuç değil. Evrende karşılığı olmayan
    # bir etiket düşer: Türkçe finans beslemeleri yazıları `BORSA` ve `FINANS`
    # gibi bölümlere koyuyor ve ikisi de "3-6 harf" testini geçiyor. İkisi de
    # enstrüman olmadığı için burada eleniyorlar.
    declared = [
        s for s in (str(x).strip().upper() for x in (item.get("related_symbols") or []))
        if s in known
    ]
    if declared:
        # Kaynak ihraççıyı biliyorsa metinden çıkarım yapılmaz: KAP bildirimleri
        # ihraççısıyla birlikte gelir ve kesin bilgiyi tahminle değiştirmek
        # olurdu.
        return sorted(set(declared))

    text = " ".join(filter(None, (item.get("title"), item.get("summary"))))
    return [row["symbol"] for row in resolve_news_symbols(text, universe)]


def resolve_news_symbols(text: str, universe: list[Any]) -> list[dict[str, str]]:
    """Bir haber metninin bağlandığı semboller, dayanağıyla birlikte.

    Ingest yolu da arşivi geri dolduran betik de BURAYI çağırır. Politikayı
    (hangi piyasaların koduyla aranacağı) iki yerde tekrarlamak, ikisinin
    ayrışması demekti -- ölçüldü: betik kısıtsız çalıştığında arşive yedi
    yanlış bağ yazıyordu.
    """
    return symbol_match.resolve_symbols(text, universe, LOCAL_TICKER_MARKETS)


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


#: Bildirim adresinin sonundaki numarayı yakalar: `.../Bildirim/1656735`.
_TRAILING_ID = re.compile(r"/(\d{3,12})/?$")


def known_news_ids(db: Session, source: str) -> list[int]:
    """Bu kaynaktan kayıtlı haberlerin adreslerindeki numaralar.

    `ingestor` bunu, hangi bildirimlerin gövdesini çekmeye gerek olmadığını
    bilmek için soruyor. Numara URL'den okunuyor: bildirimin adresi zaten
    `.../Bildirim/1656735` ve aynı bilgiyi ikinci bir sütunda saklamak,
    ikisinin ayrışabileceği bir yer açardı.
    """
    rows = (
        db.query(NewsItem.url)
        .filter(NewsItem.source == source, NewsItem.url.isnot(None))
        .all()
    )
    found = []
    for (url,) in rows:
        match = _TRAILING_ID.search(url or "")
        if match:
            found.append(int(match.group(1)))
    return sorted(set(found))
