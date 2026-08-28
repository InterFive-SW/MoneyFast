import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.investment import market_service

from . import service, social_service, stream
from .schemas import (
    CandleSeriesOut,
    FundamentalsIngestRequest,
    IngestResult,
    InstrumentListOut,
    MarketTicker,
    NewsIngestRequest,
    NewsItem,
    QuoteIngestRequest,
    SocialIngestRequest,
    SocialIngestResult,
    SocialSignalOut,
    SocialSourceType,
    SocialVerificationStatus,
)

log = logging.getLogger("moneyfast.market")

router = APIRouter(tags=["market"])

#: Symbols shown in the dashboard ticker strip, in display order. Index and FX
#: rows come from the same quotes table as everything else, so the strip and
#: the chatbot cannot disagree about a price.
TICKER_STRIP = ["XU100", "USDTRY", "EURTRY", "XAUUSD"]


def require_service_token(
    authorization: Optional[str] = Header(default=None),
) -> None:
    """Guard for the service-to-service ingest endpoints.

    These write market data the whole system then presents as fact, so they
    are not open. When BACKEND_API_KEY is unset the guard refuses rather than
    waving requests through: an ingest endpoint that silently became public
    because an env var was missing is the kind of thing nobody notices.
    """
    expected = os.getenv("BACKEND_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Ingest endpoint is not configured (BACKEND_API_KEY unset).",
        )
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid service credentials.")


@router.get("/tickers", response_model=List[MarketTicker])
async def get_market_tickers(db: Session = Depends(get_db)):
    """
    Gösterge panelindeki ticker şeridi için anlık fiyatlar.

    Veri `investment.market_quotes`'tan geliyor — sohbet botunun kullandığı
    kaynağın aynısı, dolayısıyla iki yüzeyin farklı fiyat göstermesi mümkün
    değil.

    Henüz veri toplanmadıysa boş liste döner, mock fiyat DÖNMEZ. Kullanıcı
    uydurma bir fiyatı gerçeğinden ayırt edemez; boş bir şerit, yanlış bir
    fiyattan iyidir.
    """
    quotes = market_service.latest_quotes(db, TICKER_STRIP)
    return [
        {
            "symbol": symbol,
            "currency": quotes[symbol].get("currency") or "TRY",
            "price": quotes[symbol]["price"],
            "change": quotes[symbol]["change_amount"] or 0.0,
            "changePercent": quotes[symbol]["change_percent"] or 0.0,
        }
        for symbol in TICKER_STRIP
        if symbol in quotes
    ]


@router.get("/news", response_model=List[NewsItem])
async def get_market_news(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Piyasa haber akışı.

    Aynı haberler `rag` servisine de gönderiliyor; oradaki kopya semantik
    aramaya, buradaki kopya "en yeni 20 haber" listesine hizmet ediyor. İki
    farklı erişim deseni, iki farklı depo.

    Veri yoksa boş liste döner; uydurma haber başlığı göstermek, boş bir akış
    göstermekten çok daha kötü.
    """
    return [
        {
            "id": row.id,
            "source": row.source,
            "title": row.title,
            "url": row.url or "#",
            "time": _relative_time(row.published_at),
            # Sentiment is not computed. Labelling a headline positive or
            # negative is a market view, and this system is not permitted to
            # hold one; the field stays neutral until a sourced classifier
            # exists.
            "sentiment": "neutral",
            "relatedSymbols": list(row.related_symbols or []),
        }
        for row in service.latest_news(db, limit=limit)
    ]


@router.get(
    "/instruments",
    response_model=InstrumentListOut,
    summary="Enstrüman fiyatları ve temel oranları (tarama)",
)
async def list_instruments(
    symbols: Optional[List[str]] = Query(default=None),
    sector: Optional[str] = Query(default=None),
    market: Optional[str] = Query(default=None),
    max_pe: Optional[float] = Query(default=None),
    min_pe: Optional[float] = Query(default=None),
    max_pb: Optional[float] = Query(default=None),
    sort_by: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Adı verilen enstrümanların fiyatı ve temel oranları, ya da bir tarama.

    Sohbet botunun `get_market_data` tool'u buradan besleniyor: "THYAO kaç
    lira?" ve "F/K'sı 10'un altındaki hisseler" aynı uç noktadan cevaplanıyor.

    Temel oran filtreleri, değeri NULL olan satırları **eler**. "F/K'sı 10'un
    altında" sorgusu sessizce "F/K'sı 10'un altında ya da bilinmiyor" anlamına
    gelmemeli; verisi olmayan bir hisse ucuz görünmemeli.
    """
    filters = {
        "sector": sector,
        "market": market,
        "max_pe": max_pe,
        "min_pe": min_pe,
        "max_pb": max_pb,
    }
    try:
        rows = market_service.list_instruments(
            db,
            symbols=symbols,
            filters={k: v for k, v in filters.items() if v is not None},
            limit=limit,
            sort_by=sort_by,
        )
    except market_service.UnknownSortError as exc:
        # 400, not 500: the request is malformed, and the message names the
        # valid values so the caller can correct itself.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Wrapped in an object rather than returned as a bare array: every other
    # backend endpoint returns one, and the MCP client rejects a non-object
    # body as a contract violation.
    # Queries that did not settle travel back with what they might have
    # meant. Dropping them silently is how "koz" became a bare "bulunamadı"
    # when KOZAL and KOZAA were both sitting right there.
    return {
        "instruments": rows,
        "unresolved": market_service.symbol_suggestions(db, symbols),
    }


@router.get(
    "/candles",
    response_model=CandleSeriesOut,
    summary="Bir enstrümanın günlük mum verisi",
)
async def get_candles(
    symbol: str = Query(..., min_length=1),
    limit: int = Query(default=180, ge=2, le=400),
    db: Session = Depends(get_db),
):
    """
    Gerçek günlük OHLCV barları — grafiklerin okuduğu yer.

    Bu uç nokta olmadan karşılaştırma grafikleri tohumlanmış bir rastgele sayı
    üretecinden besleniyordu: veriler zaten `market_candles` içindeydi, onları
    dışarı veren bir yol yoktu.

    Bilinmeyen sembol boş bir seri döndürür, hata değil: "bu enstrümanın
    geçmişi yok" bir cevaptır ve grafik onu boş çizebilir.
    """
    product = market_service.resolve_symbol(db, symbol)
    if product is None:
        return {
            "symbol": symbol.upper(),
            "currency": "TRY",
            "interval": "1d",
            "candles": [],
        }
    return {
        "symbol": product.symbol,
        "currency": product.currency_code or "TRY",
        "interval": "1d",
        "candles": market_service.candle_series(db, product.symbol, limit=limit),
    }


@router.get(
    "/stream",
    summary="Canlı fiyat akışı (Server-Sent Events)",
)
async def market_stream(request: Request):
    """
    Fiyat güncellemelerini SSE ile iter.

    Tek bir arka plan görevi veritabanını okur ve tüm abonelere dağıtır; on
    açık panel, on kat veritabanı yükü anlamına gelmiyor. Bağlantı kopmalarına
    karşı düzenli aralıklarla yorum satırı (heartbeat) gönderilir — aksi halde
    araya giren proxy'ler boşta duran akışı kapatır.
    """
    queue = await stream.subscribe()

    async def events():
        try:
            # The current frame immediately, so a page that opens between two
            # ticks is not blank until the next one.
            snapshot = stream.latest_frame()
            if snapshot:
                yield f"event: quotes\ndata: {json.dumps(snapshot)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    frame = await asyncio.wait_for(
                        queue.get(), timeout=stream.HEARTBEAT_SECONDS
                    )
                    yield f"event: quotes\ndata: {json.dumps(frame)}\n\n"
                except asyncio.TimeoutError:
                    # A comment line: valid SSE, ignored by EventSource, and
                    # enough traffic to keep an idle connection open.
                    yield ": keepalive\n\n"
        finally:
            stream.unsubscribe(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Without this an nginx in front would buffer the stream and
            # deliver everything at once when the connection closes.
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/ingest",
    response_model=IngestResult,
    summary="Fiyat ve mum verisi yükle (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
async def ingest_market_data(
    request: QuoteIngestRequest, db: Session = Depends(get_db)
):
    """`ingestor` servisinin fiyat ve OHLCV verisi yazdığı uç nokta."""
    quotes = market_service.upsert_quotes(db, [q.model_dump() for q in request.quotes])
    candles = market_service.upsert_candles(
        db, [c.model_dump() for c in request.candles]
    )
    log.info("ingested %d quotes and %d new candles", quotes, candles)
    return {"quotes_written": quotes, "candles_written": candles, "news_written": 0}


@router.get(
    "/candles/coverage",
    summary="Mum verisi kapsaması (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
async def candle_coverage(db: Session = Depends(get_db)):
    """`ingestor`'ın açılışta neyi geri dolduracağını sorduğu uç nokta.

    Sembol başına kaç günlük bar tutulduğunu ve en yenisinin tarihini döner.
    Bunu sormadan geri doldurmak, her yeniden başlatmada 187 sembolün
    tamamını sağlayıcıdan tekrar istemek demekti.
    """
    return market_service.candle_coverage(db)


@router.post(
    "/news/ingest",
    response_model=IngestResult,
    summary="Haber yükle (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
async def ingest_news(request: NewsIngestRequest, db: Session = Depends(get_db)):
    written = service.upsert_news(db, [item.model_dump() for item in request.items])
    log.info("ingested %d new news items of %d offered", written, len(request.items))
    return {"quotes_written": 0, "candles_written": 0, "news_written": written}


@router.post(
    "/social/ingest",
    response_model=SocialIngestResult,
    summary="Normalize edilmiş sosyal sinyalleri yükle (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
async def ingest_social(request: SocialIngestRequest, db: Session = Depends(get_db)):
    """Atomically persist an ingestor batch; no upstream credential is accepted."""

    try:
        result = social_service.ingest_batch(
            db,
            [item.model_dump() for item in request.accounts],
            [item.model_dump() for item in request.posts],
        )
    except social_service.SocialBatchConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except social_service.SocialBatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    log.info(
        "social ingest: %d inserted, %d updated, %d duplicate, %d unresolved",
        result["posts_inserted"],
        result["posts_updated"],
        result["posts_duplicate"],
        result["instruments_unresolved"],
    )
    return result


@router.get(
    "/social-signals",
    response_model=List[SocialSignalOut],
    summary="Doğrulanma durumu etiketli sosyal piyasa sinyalleri",
)
async def social_signals(
    symbol: Optional[str] = Query(default=None, min_length=1, max_length=255),
    since_hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=20, ge=1, le=100),
    minimum_trust_score: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    verification_status: Optional[SocialVerificationStatus] = Query(default=None),
    source_type: Optional[SocialSourceType] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Public like other non-user-specific market reads; raw metadata is omitted."""

    return social_service.list_signals(
        db,
        symbol=symbol,
        since_hours=since_hours,
        limit=limit,
        minimum_trust_score=minimum_trust_score,
        verification_status=verification_status,
        source_type=source_type,
    )


@router.post(
    "/fundamentals/ingest",
    response_model=IngestResult,
    summary="Temel oranları yükle (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
async def ingest_fundamentals(
    request: FundamentalsIngestRequest, db: Session = Depends(get_db)
):
    """
    Değerleme oranlarını günceller.

    Eksik değerler NULL olarak yazılır, sıfıra çevrilmez: kazanç verisi
    yayımlanmayan bir şirket, "en düşük F/K" taramasının başında görünmemeli.
    """
    written = market_service.upsert_fundamentals(
        db, [i.model_dump() for i in request.items]
    )
    log.info("ingested fundamentals for %d instruments", written)
    return {
        "quotes_written": 0,
        "candles_written": 0,
        "news_written": 0,
        "fundamentals_written": written,
    }


def _relative_time(moment: datetime) -> str:
    """Turkish relative timestamp for the feed, e.g. "5 dk önce"."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    minutes = int((datetime.now(timezone.utc) - moment).total_seconds() // 60)
    if minutes < 1:
        return "az önce"
    if minutes < 60:
        return f"{minutes} dk önce"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} saat önce"
    return f"{hours // 24} gün önce"


@router.get("/health", summary="Market modülü sağlık durumu")
async def health_check():
    """
    Market modülünün durumunu (health check) kontrol eder.
    """
    return {"status": "ok", "module": "market"}
