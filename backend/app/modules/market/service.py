"""News storage and retrieval for the dashboard feed."""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

import httpx

from sqlalchemy import text
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


def upsert_news(
    db: Session, items: list[dict[str, Any]]
) -> tuple[int, dict[str, list[str]], list[dict[str, Any]]]:
    """Store articles, ignoring ones already held.

    Deduplicated on content_hash rather than URL: the same wire story is
    republished under different URLs, and a feed that renumbers its links
    would otherwise re-import its whole history every poll.

    Yazılan satır sayısının YANINDA çözülen semboller de dönüyor, hash'e göre.
    Çözümleme burada yapılıyor ve bir dönem burada KALIYORDU: `ingestor`
    haberi önce buraya, sonra RAG'a yazıyor ve RAG'a giden kopya kendi (boş)
    etiket listesini taşıyordu. Ölçüldü -- korpustaki 1.970 RSS belgesinin
    SIFIRINDA ticker vardı, yani ajanın `tickers` filtresi yalnızca KAP
    bildirimlerinde çalışıyordu, çünkü onlar etiketi kaynağından getiriyor.

    Harita, YAZILANLAR için değil TEKLİF EDİLENLER için dönüyor: backend'de
    zaten duran bir haber RAG'da eksik olabilir (iki yazma ayrı istekler) ve
    o durumda tek şansı budur.

    Üçüncü dönen değer bunun TERSİ: yalnızca GERÇEKTEN eklenen ve bir sembole
    bağlanan haberler. Bildirim üretimi buna bakıyor -- zaten duran bir haberi
    yeniden bildirmek, akışı otuz saniyede bir tekrar eden bir gürültüye
    çevirirdi.
    """
    if not items:
        return 0, {}, []

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

    # `RETURNING`: hangi satırların GERÇEKTEN eklendiğini söylüyor, kaç tane
    # olduğunu değil. Bildirim yalnızca yeni haber için üretilmeli ve
    # `rowcount` bunu ayırt etmiyordu -- her turda aynı haberi yeniden
    # bildirmek, akışı otuz saniyede bir tekrar eden bir gürültüye çevirirdi.
    statement = (
        insert(NewsItem)
        .values(payload)
        .on_conflict_do_nothing(index_elements=["content_hash"])
        .returning(NewsItem.id, NewsItem.content_hash)
    )
    inserted = db.execute(statement).all()
    db.commit()
    resolved = {
        row["content_hash"]: row["related_symbols"]
        for row in payload
        if row["related_symbols"]
    }
    by_hash = {row["content_hash"]: row for row in payload}
    # Eklenen ve BİR SEMBOLE bağlanan haberler, bildirim için.
    fresh = [
        {
            "id": str(news_id),
            "title": by_hash[content_hash]["title"],
            "symbols": by_hash[content_hash]["related_symbols"],
        }
        for news_id, content_hash in inserted
        if by_hash.get(content_hash, {}).get("related_symbols")
    ]
    return len(inserted), resolved, fresh


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

    found = resolve_item_symbols(
        item.get("source"), item.get("title"), item.get("summary"), universe
    )
    return [row["symbol"] for row in found]


#: Bildirim kaynakları: gövdesinde ilgili tarafları -- yönetim kurulu
#: üyesinin başka şirketteki görevini, ana ortaklığı, likidite sağlayıcıyı --
#: sayan kaynaklar.
FILING_SOURCES = frozenset({"KAP"})


def resolve_item_symbols(
    source: str | None, title: str | None, summary: str | None, universe: list[Any]
) -> list[dict[str, str]]:
    """Bir haber satırının bağlandığı semboller. Bildirimlerde kısa ad dar.

    Kısa ad ("thy", "opet") bir bildirimin GÖVDESİNDE, o bildirimin konusu
    olmayan bir şirketi işaret ediyor: KAP formları ilgili tarafları tek tek
    sayıyor. Ölçüldü, kural arşivde 16 farklı (sembol, konu) çiftini
    düşürüyor ve elle bakıldığında on altısı da yanlış:

      "TÜRKİYE GARANTİ BANKASI A.Ş. — Şirket Genel Bilgi Formu"  -> TKFEN
      "OTOKAR OTOMOTİV VE SAVUNMA SANAYİ A.Ş. — ..."             -> YKBNK
      "EMLAK KATILIM VARLIK KİRALAMA A.Ş. — ..."                 -> THYAO

    Kısıt YALNIZCA kısa ada. Açık kod ve resmî ad gövdede de okunmaya devam
    ediyor, çünkü orada güvenilirler: BISTECH devre kesici bildirimlerinin
    başlığı jenerik ("BORSA İSTANBUL BISTECH DEVRE KESİCİ UYGULAMASI") ve
    konu şirket yalnızca gövdede, açık koduyla yazılı. Metnin tamamını
    başlığa indirgemek bu bildirimlerin 550'sini birden koparıyordu.

    Haber kaynaklarına hiç dokunulmuyor: "Borsada bugün" başlıklı bir yazı
    gerçekten gövdesinde saydığı hisseler hakkındadır.
    """
    text = " ".join(filter(None, (title, summary)))
    found = resolve_news_symbols(text, universe)
    if (source or "").strip().upper() not in FILING_SOURCES:
        return found
    in_title = {row["symbol"] for row in resolve_news_symbols(title or "", universe)}
    return [
        row
        for row in found
        if row["basis"] != "ALIAS" or row["symbol"] in in_title
    ]


def resolve_news_symbols(text: str, universe: list[Any]) -> list[dict[str, str]]:
    """Bir haber metninin bağlandığı semboller, dayanağıyla birlikte.

    Ingest yolu da arşivi geri dolduran betik de BURAYI çağırır. Politikayı
    (hangi piyasaların koduyla aranacağı) iki yerde tekrarlamak, ikisinin
    ayrışması demekti -- ölçüldü: betik kısıtsız çalıştığında arşive yedi
    yanlış bağ yazıyordu.
    """
    return symbol_match.resolve_symbols(text, universe, LOCAL_TICKER_MARKETS)


def news_coverage(db: Session) -> dict[str, dict]:
    """Kaynak başına: kaç haber var, en yenisi ne zaman, en yüksek numara.

    `candle_coverage` ile aynı soru, haberler için. Ama bir fark var:
    KAP bildirim numarası MONOTON artıyor, dolayısıyla "elimizdeki en yüksek
    numara" bir tarihten hem daha ucuz hem daha kesin bir su seviyesi.

    Numara için ayrı bir sütun YOK ve gerekmiyor: kalıcı bağlantının kendisi
    numarayı taşıyor (`/tr/Bildirim/1655982`) ve o bağlantı atıf için zaten
    saklanıyor.

    **Bu bir su seviyesi, tamlık kanıtı değil.** Yarıda kesilmiş bir tur,
    en yüksek numaranın ALTINDA boşluk bırakır; onu `known-ids` yakalar.
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


def news_archive(
    db: Session, source: str, limit: int, offset: int
) -> list[NewsItem]:
    """Saklanan bildirimler, yeniden eskiye.

    `latest_news`'ten ayrı: o pano beslemesi (yirmi satır, kaynak farketmez),
    bu arşivi kapatan iş için sayfalanmış bir tarama. Yeniden eskiye,
    `topup`/`backfill` ile aynı gerekçeyle: yarıda kesilen bir tur bitişik ve
    GÜNCEL bir arşiv bırakır, rastgele bir serpinti değil.
    """
    return (
        db.query(NewsItem)
        .filter(NewsItem.source == source)
        .order_by(NewsItem.published_at.desc(), NewsItem.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


def latest_news(
    db: Session,
    limit: int = 20,
    symbols: Optional[Sequence[str]] = None,
) -> list[NewsItem]:
    """En yeni haberler; `symbols` verilirse yalnızca o hisselere bağlı olanlar.

    Süzgeç sunucuda, çünkü istemci tarafında süzmek yalnızca ÇEKİLEN satırları
    daraltabiliyor: hisse detay sayfası "en yeni 20" içinden AAPL'i ayıklamaya
    çalıştığında, o yirmide AAPL yoksa sonuç "bu hissenin haberi yok" gibi
    okunuyor -- oysa soru hiç sorulmamış oluyor.

    `portfolio_news` ile aynı `overlap` deseni; orası kullanıcının
    pozisyonlarını, burası çağıranın verdiği listeyi kullanıyor.
    """
    query = db.query(NewsItem)
    wanted = [symbol for symbol in dict.fromkeys(symbols or []) if symbol]
    if wanted:
        query = query.filter(NewsItem.related_symbols.overlap(wanted))
    return (
        query.order_by(NewsItem.published_at.desc(), NewsItem.id.desc())
        .limit(limit)
        .all()
    )


# ── Portföye dokunan haberler ────────────────────────────────────────────────

#: Panelin baktığı pencere. Sayı ve başlıklar AYNI pencereden okunur:
#: "AKBNK: 9 haber" yazıp listede o dokuzun dışından bir başlık göstermek,
#: sayının neyi saydığını okunamaz hâle getirirdi.
#:
#: Doksan gün, otuz değil. Sebep eşleştirmenin bilinçli olarak dar olması:
#: ölçüldü, son otuz günün 1.096 RSS haberinin yalnızca 21'i (%2) bir sembole
#: bağlanıyor -- bulanık eşleşme olmadığı için. Aynı test portföyünde otuz gün
#: TEK bir başlık, doksan gün dokuz başlık veriyor. Haberin tarihi zaten her
#: satırda yazılı, dolayısıyla eski bir başlık yeni gibi görünmüyor; boş bir
#: panel ise "haber yok" değil "böyle bir şey yok" diye okunuyor.
#: Eşleşme kapsamı arttığında bu sayı yeniden ölçülüp daraltılabilir.
NEWS_WINDOW_DAYS = 90


def portfolio_news(
    db: Session,
    symbols: Sequence[str],
    limit: int = 20,
    days: int = NEWS_WINDOW_DAYS,
) -> tuple[list[NewsItem], dict[str, int]]:
    """Kullanıcının tuttuğu sembollere bağlı haberler ve sembol başına sayı.

    Tek okuma, iki cevap: pencere içindeki eşleşen satırların tamamı okunur,
    sembol başına sayılır, sonra `limit` kadarı başlık olarak döner. Sayıyı
    ayrı bir sorgudan almak, iki sorgunun arasında gelen bir haberin sayıda
    görünüp listede görünmemesi demekti.

    Haberler ZAMAN SIRASINDA döner, sembole göre paylaştırılmaz. Portföyün
    bir hissesi haberlerin tamamını doldurabilir ve bu gerçeğin kendisidir;
    sembol başına sayı zaten dağılımı gösteriyor. Yapay olarak her sembolden
    bir başlık seçmek, o gün gerçekten ne olduğunu gizlerdi.
    """
    wanted = [symbol for symbol in dict.fromkeys(symbols) if symbol]
    if not wanted:
        return [], {}

    since = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    rows = (
        db.query(NewsItem)
        .filter(
            NewsItem.published_at >= since,
            NewsItem.related_symbols.overlap(wanted),
        )
        .order_by(NewsItem.published_at.desc(), NewsItem.id.desc())
        .all()
    )

    counts = {symbol: 0 for symbol in wanted}
    for row in rows:
        for symbol in row.related_symbols or []:
            if symbol in counts:
                counts[symbol] += 1
    return rows[:limit], counts


def held_symbols(holdings: Sequence[dict[str, Any]]) -> list[str]:
    """Pozisyon listesinden semboller, sırası korunarak ve tekilleştirilerek.

    Sıfır adetli bir pozisyon dışarıda kalır: kapanmış bir pozisyonun haberi
    "portföyünüze dokunan haber" değildir.
    """
    return list(
        dict.fromkeys(
            holding["symbol"]
            for holding in holdings
            if holding.get("symbol") and float(holding.get("quantity") or 0) > 0
        )
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
