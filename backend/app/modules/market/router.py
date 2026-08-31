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
from . import service, stream, technicals
from .schemas import (
    IngestResult,
    FundamentalsIngestRequest,
    CandleSeriesOut,
    InstrumentListOut,
    InstrumentSuggestion,
    MarketHeatmapOut,
    MarketTicker,
    NewsIngestRequest,
    NewsItem,
    QuoteIngestRequest,
    TechnicalSignalsOut,
    FundamentalsOut,
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
def get_market_tickers(db: Session = Depends(get_db)):
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
def get_market_news(
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
    "/heatmap",
    response_model=MarketHeatmapOut,
    summary="Piyasa ısı haritası (piyasa değeri ve günlük değişim)",
)
def market_heatmap(
    market: Optional[str] = Query(default=None),
    limit: int = Query(default=300, ge=1, le=600),
    db: Session = Depends(get_db),
):
    """Bir endeksin ısı haritası.

    `GET /api/investment/heatmap` ile karıştırılmamalı: o, kullanıcının
    portföyünü pozisyon ağırlığına göre gösteriyor. Bu, piyasanın kendisini
    gösteriyor -- her hisse piyasa değeri kadar yer kaplıyor.

    `market` bir borsa (BIST, NASDAQ) ya da bir endeks (SP500) olabilir; aynı
    alan ikisini de taşıyor çünkü AAPL Nasdaq'ta işlem görür VE S&P 500
    üyesidir.
    """
    return market_service.market_heatmap(db, market=market, limit=limit)


@router.get(
    "/search",
    response_model=List[InstrumentSuggestion],
    summary="Enstrüman arama (yazdıkça öneri)",
)
def search_instruments(
    q: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(default=10, ge=1, le=25),
    db: Session = Depends(get_db),
):
    """Sembol ya da şirket adına göre öneri listesi.

    Evren binin üzerinde enstrüman; bir açılır liste bunu taşıyamaz. Türkçe
    katlama `market_service._fold` ile yapılıyor, dolayısıyla `sise` yazan
    `ŞİŞE`yi buluyor.
    """
    return market_service.search_instruments(db, q, limit=limit)

@router.get(
    "/instruments",
    response_model=InstrumentListOut,
    summary="Enstrüman fiyatları ve temel oranları (tarama)",
)
def list_instruments(
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
    # Adı verilen bir enstrüman sorulduğunda fiyat ÖNCE tazelenir.
    #
    # Toplu tur on beş dakikada bir dönüyor; ekranlar için yeterli, "THYAO kaç
    # TL" sorusu için değil. Tarama sorgularında yapılmaz: bir tarama yüzlerce
    # satır okur ve hiçbiri tek bir anlık fiyata bağlı karar değildir.
    #
    # Başarısız olursa sessizce devam edilir -- elde olan fiyat, cevapsız
    # kalmaktan iyidir.
    if symbols:
        service.refresh_quotes(symbols)

    filters = {
        "sector": sector, "market": market,
        "max_pe": max_pe, "min_pe": min_pe, "max_pb": max_pb,
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
def get_candles(
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
        return {"symbol": symbol.upper(), "currency": "TRY", "interval": "1d", "candles": []}
    return {
        "symbol": product.symbol,
        "currency": product.currency_code or "TRY",
        "interval": "1d",
        "candles": market_service.candle_series(db, product.symbol, limit=limit),
    }


@router.get(
    "/fundamentals",
    response_model=FundamentalsOut,
    summary="Bir enstrümanın temel verisi ve kârlılık oranları",
)
def get_fundamentals(
    symbol: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    """
    Gelir tablosu, marjlar, kârlılık, borç ve analist konsensüsü.

    Sohbet ile Piyasalar ekranları AYNI uç noktayı okuyor. Bilinmeyen sembol
    ya da henüz çekilmemiş temel veri, boş bir kayıt döndürür -- hata değil:
    "bu enstrümanın temel verisi yok" bir cevaptır ve ekran onu boş
    çizebilir.
    """
    product = market_service.resolve_symbol(db, symbol)
    if product is None:
        return {"symbol": symbol.upper()}
    return market_service.fundamentals_for(db, product.symbol) or {
        "symbol": product.symbol,
        "name": product.name,
        "currency": product.currency_code or "TRY",
    }


@router.get(
    "/technicals",
    response_model=TechnicalSignalsOut,
    summary="Bir enstrümanın teknik göstergeleri ve Türkçe okuması",
)
def get_technicals(
    symbol: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    """
    Hareketli ortalamalar, RSI, 52 hafta aralığındaki konum ve eğilim.

    Sohbet ile hisse detay sayfası AYNI uç noktayı okuyor. Ayrı hesaplasalardı
    ikisi aynı hisse için farklı bir eğilim söyleyebilirdi -- risk ölçümünün
    tek yerde toplanma sebebiyle aynı sebep.

    `narrative` kullanıcıya gösterilecek cümlenin kendisi. Sayıları modele
    verip "yorumla" demek, aynı göstergelerin her turda biraz farklı
    anlatılması demekti; hangi durumun hangi ifadeye karşılık geldiği kodda.

    Bilinmeyen sembol boş bir ölçüm döndürür, hata değil.
    """
    product = market_service.resolve_symbol(db, symbol)
    if product is None:
        return {
            "symbol": symbol.upper(),
            "currency": "TRY",
            "signals": technicals.compute([]),
            "narrative": None,
        }
    # 260 bar: en uzun pencere 200 günlük ortalama, 52 hafta aralığı 252.
    bars = market_service.candle_series(db, product.symbol, limit=technicals.BARS_NEEDED)
    signals = technicals.compute(bars)
    return {
        "symbol": product.symbol,
        "currency": product.currency_code or "TRY",
        "signals": signals,
        "narrative": technicals.narrate(product.symbol, signals),
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
                    frame = await asyncio.wait_for(queue.get(), timeout=stream.HEARTBEAT_SECONDS)
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
def ingest_market_data(request: QuoteIngestRequest, db: Session = Depends(get_db)):
    """`ingestor` servisinin fiyat ve OHLCV verisi yazdığı uç nokta."""
    quotes = market_service.upsert_quotes(db, [q.model_dump() for q in request.quotes])
    candles = market_service.upsert_candles(db, [c.model_dump() for c in request.candles])
    log.info("ingested %d quotes and %d new candles", quotes, candles)
    return {"quotes_written": quotes, "candles_written": candles, "news_written": 0}


@router.get(
    "/candles/coverage",
    summary="Mum verisi kapsaması (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
def candle_coverage(db: Session = Depends(get_db)):
    """`ingestor`'ın açılışta neyi geri dolduracağını sorduğu uç nokta.

    Sembol başına kaç günlük bar tutulduğunu ve en yenisinin tarihini döner.
    Bunu sormadan geri doldurmak, her yeniden başlatmada 187 sembolün
    tamamını sağlayıcıdan tekrar istemek demekti.
    """
    return market_service.candle_coverage(db)


@router.get(
    "/candles/intraday-symbols",
    summary="Gün içi bar gereken semboller (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
def intraday_symbols(db: Session = Depends(get_db)):
    """`ingestor`'ın gün içi bar çekeceği kümeyi sorduğu uç nokta.

    Evrenin tamamı değil: gün içi seriye ihtiyaç duyan tek ekran portföy
    performansı, dolayısıyla yalnızca tutulan, izlenen ve kur/endeks
    enstrümanları. Bin enstrümanın 15 dakikalık barlarını sürekli çekmek,
    gereğinden kat kat fazla istek olurdu.
    """
    return {"symbols": market_service.intraday_symbols(db)}


@router.get(
    "/fundamentals/missing",
    summary="Temel verisi eksik enstrümanlar (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
def fundamentals_missing(db: Session = Depends(get_db)):
    """`ingestor`'ın açılışta neyi dolduracağını sorduğu uç nokta.

    Yalnızca eksik olanlar: hepsini her açılışta yeniden çekmek, çeyreklik
    raporlarla değişen oranları durmadan yeniden yazmak olurdu.
    """
    return {"symbols": market_service.symbols_without_fundamentals(db)}


@router.post(
    "/news/ingest",
    response_model=IngestResult,
    summary="Haber yükle (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
def ingest_news(request: NewsIngestRequest, db: Session = Depends(get_db)):
    written = service.upsert_news(db, [item.model_dump() for item in request.items])
    log.info("ingested %d new news items of %d offered", written, len(request.items))
    return {"quotes_written": 0, "candles_written": 0, "news_written": written}


@router.post(
    "/fundamentals/ingest",
    response_model=IngestResult,
    summary="Temel oranları yükle (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
def ingest_fundamentals(request: FundamentalsIngestRequest, db: Session = Depends(get_db)):
    """
    Değerleme oranlarını günceller.

    Eksik değerler NULL olarak yazılır, sıfıra çevrilmez: kazanç verisi
    yayımlanmayan bir şirket, "en düşük F/K" taramasının başında görünmemeli.
    """
    written = market_service.upsert_fundamentals(db, [i.model_dump() for i in request.items])
    log.info("ingested fundamentals for %d instruments", written)
    return {"quotes_written": 0, "candles_written": 0, "news_written": 0,
            "fundamentals_written": written}


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


@router.get(
    "/health",
    summary="Market modülü sağlık durumu"
)
async def health_check():
    """
    Market modülünün durumunu (health check) kontrol eder.
    """
    return {"status": "ok", "module": "market"}
