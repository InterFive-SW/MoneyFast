import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_id, require_service_token
from app.modules.investment import ai_service, market_service
from app.modules.notification import service as notification_service
from . import funds as funds_service
from . import service, stream, technicals
from .schemas import (
    CandleSeriesOut,
    FundCandleSeriesOut,
    FundIngestRequest,
    FundListOut,
    FundOut,
    FundSeriesOut,
    FundamentalsIngestRequest,
    FundamentalsOut,
    IngestResult,
    InstrumentListOut,
    InstrumentSuggestion,
    MarketCalendarOut,
    MarketHeatmapOut,
    MarketTicker,
    NewsIngestRequest,
    NewsItem,
    PortfolioNewsOut,
    PortfolioTechnicalOut,
    QuarterlyIngestRequest,
    QuarterlyOut,
    QuoteIngestRequest,
    SessionStateRequest,
    TechnicalSignalsOut,
)

log = logging.getLogger("moneyfast.market")

router = APIRouter(tags=["market"])

#: Symbols shown in the dashboard ticker strip, in display order. Index and FX
#: rows come from the same quotes table as everything else, so the strip and
#: the chatbot cannot disagree about a price.
TICKER_STRIP = ["XU100", "USDTRY", "EURTRY", "XAUUSD"]




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
    symbols: Optional[List[str]] = Query(
        default=None,
        description="Yalnızca bu hisselere bağlı haberler. Tekrarlanan anahtar.",
    ),
    db: Session = Depends(get_db),
):
    """
    Piyasa haber akışı.

    Aynı haberler `rag` servisine de gönderiliyor; oradaki kopya semantik
    aramaya, buradaki kopya "en yeni 20 haber" listesine hizmet ediyor. İki
    farklı erişim deseni, iki farklı depo.

    `symbols` verilirse süzgeç SORGUDA uygulanır, dönen sayfada değil. Fark
    şurada: hisse detay sayfası "en yeni 20"yi çekip içinden AAPL'i ayıklarsa,
    o yirmide AAPL yoksa ekranda "haber yok" yazıyor -- oysa soru hiç
    sorulmamış oluyor.

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
        for row in service.latest_news(db, limit=limit, symbols=symbols)
    ]



@router.get(
    "/news/portfolio",
    response_model=PortfolioNewsOut,
    summary="Portföye dokunan haberler (oturum sahibinin pozisyonları)",
)
def get_portfolio_news(
    limit: int = Query(default=20, ge=1, le=100),
    days: int = Query(default=service.NEWS_WINDOW_DAYS, ge=1, le=365),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Kullanıcının tuttuğu hisselere bağlı haberler.

    Oturum ZORUNLU, demo portföyüne düşülmüyor. Okuma uçlarının çoğu anonim
    çağrıyı demo hesabına düşürüyor ve bu zararsız -- ama "portföyünüze
    dokunan haberler" başlığı altında başkasının portföyünün haberlerini
    göstermek, izleme listesinin eskiden yaptığı hatanın aynısı olurdu:
    kullanıcının seçmediği bir listeyi onunmuş gibi sunmak.

    Haberler YORUMLANMIYOR. Başlık, kaynak ve tarih veriliyor; bir haberin
    olumlu ya da olumsuz olduğu söylenmiyor, çünkü bu bir piyasa görüşüdür ve
    bu sistemin görüş tutma izni yok.
    """
    return _portfolio_news_payload(db, user_id, limit=limit, days=days)


@router.get(
    "/news/portfolio/{user_id}",
    response_model=PortfolioNewsOut,
    summary="Portföye dokunan haberler (MCP sözleşmesi)",
    # Konusunu YOLDA adlandıran her uç gibi korunuyor. Oturum kapsamlı ikizi
    # (`/news/portfolio`) kullanıcıyı token'dan çözer ve yalnızca çağıranın
    # kendi verisini döndürebilir; bu döndüremez. Korumasızken bir kullanıcı
    # id'si bilen herkes o kişinin TUTTUĞU SEMBOLLERİ okuyabiliyordu.
    dependencies=[Depends(require_service_token)],
)
def get_portfolio_news_for_ai(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    days: int = Query(default=service.NEWS_WINDOW_DAYS, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """
    Yukarıdakiyle aynı veri, kullanıcısı yoldan gelen hâli.

    `get_portfolio_positions`'ın deseni: MCP araçları kullanıcıyı doğrulanmış
    oturum zarfından alıp yola koyar, bearer token taşımaz. İkisi TEK bir
    yardımcıyı çağırıyor, böylece panel ile sohbetin kullanıcının neye sahip
    olduğu ya da hangi haberin ona dokunduğu konusunda ayrışması mümkün değil.
    """
    return _portfolio_news_payload(db, user_id, limit=limit, days=days)


def _portfolio_news_payload(db: Session, user_id: str, limit: int, days: int) -> dict:
    """İki ucun ortak gövdesi."""
    holdings = market_service.holdings(db, user_id=user_id)
    symbols = service.held_symbols(holdings)
    names = {holding["symbol"]: holding.get("name") or holding["symbol"] for holding in holdings}
    rows, counts = service.portfolio_news(db, symbols, limit=limit, days=days)
    held = set(symbols)
    return {
        "symbols": [
            {"symbol": symbol, "name": names.get(symbol, symbol), "count": counts.get(symbol, 0)}
            for symbol in symbols
        ],
        "items": [
            {
                "id": row.id,
                "source": row.source,
                "title": row.title,
                "url": row.url or "#",
                "time": _relative_time(row.published_at),
                "publishedAt": row.published_at,
                "sentiment": "neutral",
                "relatedSymbols": list(row.related_symbols or []),
                "heldSymbols": [s for s in (row.related_symbols or []) if s in held],
            }
            for row in rows
        ],
        "windowDays": days,
    }


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
    #: Tavan evrenin tamamını kapsıyor (1.014 enstrüman, ölçülen 426 KB).
    #:
    #: Sunucu tarafı sayfalama DEĞİL: süzgeç paneli (F/K, PD/DD, piyasa
    #: değeri, değişim %) istemcide çalışıyor ve bir SAYFA üzerinde
    #: çalıştırılsaydı "F/K'sı 10'un altı" sorgusu yalnızca o sayfaya düşen
    #: eşleşmeleri gösterirdi -- `useInstruments`'ın kendi yorumunun zaten
    #: uyardığı hata. Ekran sayfalamayı 15'erlik dilimlerle kendi yapıyor.
    limit: int = Query(default=20, ge=1, le=1200),
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
    "/calendar",
    response_model=MarketCalendarOut,
    summary="Analist konsensüsü, temettü ve bilanço takvimi",
)
def get_calendar(
    limit: int = Query(default=40, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """"Analizler" ekranının üç listesi.

    Enstrüman başına ayrı istek yerine tek sorgu: ekran otuz satır gösteriyor
    ve otuz istek atmak, göstereceği şeyden pahalı olurdu.
    """
    return market_service.calendar_rows(db, limit=limit)


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
    "/portfolio/technical",
    response_model=PortfolioTechnicalOut,
    summary="Portföy geneli teknik görünüm",
)
def get_portfolio_technical(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Her pozisyonun teknik durumu ve portföy geneli toplulaştırma.

    `market` modülünde, `investment`ta değil. Teknik motor burada ve bu modül
    zaten `investment.market_service`'i okuyor; uç noktayı investment'a koymak
    iki modül arasında ÇİFT YÖNLÜ bir bağımlılık açardı (`market.technicals`
    da `risk.returns`'ü okuyor, yani zincir zaten tek yönlü kurulu). Yolu
    değil, bağımlılık yönünü korumak önemli.

    Sayfadaki tek hisse görünümüyle aynı `compute`/`narrate` çağrılıyor: iki
    yüzeyin aynı hisse için farklı bir eğilim söylemesi mümkün değil.
    """
    return _portfolio_technical_payload(db, user_id)


@router.get(
    "/portfolio/technical/{user_id}",
    response_model=PortfolioTechnicalOut,
    summary="Portföy geneli teknik görünüm (MCP sözleşmesi)",
    dependencies=[Depends(require_service_token)],
)
def get_portfolio_technical_for_ai(user_id: str, db: Session = Depends(get_db)):
    """
    Yukarıdakiyle aynı veri, kullanıcısı yoldan gelen hâli.

    `get_portfolio_positions` ve `news/portfolio` ile aynı desen: MCP araçları
    kullanıcıyı doğrulanmış oturum zarfından alıp yola koyar. İkisi TEK bir
    yardımcıyı çağırıyor, böylece panelin ve sohbetin aynı portföy için farklı
    bir eğilim söylemesi mümkün değil.
    """
    return _portfolio_technical_payload(db, user_id)


def _portfolio_technical_payload(db: Session, user_id: str) -> dict:
    """İki ucun ortak gövdesi."""
    holdings = market_service.holdings(db, user_id=user_id)
    rates = ai_service.fx_rates(market_service.latest_quotes(db))
    # `holding_value`'ın varsayılanıyla aynı; ekranın para birimi ürün
    # genelinde TRY ve ayrı bir sabit tanımlamak, ikisinin ayrışabileceği
    # bir yer açardı.
    base = "TRY"

    rows, unconvertible = [], []
    for holding in holdings:
        symbol = holding["symbol"]
        bars = market_service.candle_series(db, symbol, limit=technicals.BARS_NEEDED)
        signals = technicals.compute(bars)
        # Değer, taban para birimine çevrilmiş hâliyle. Çevrilemeyen pozisyon
        # None kalır ve ağırlık hesabına girmez -- kuru olmayan bir pozisyonu
        # 1.0 ile çevirmek, 15.098 TL'lik bir varlığı 315 TL saymak demekti.
        value = ai_service.holding_value(holding, rates, base)
        if value is None:
            unconvertible.append(symbol)
        rows.append(
            {
                "symbol": symbol,
                "name": holding.get("name") or symbol,
                "currency": holding.get("currency") or base,
                "signals": signals,
                "narrative": technicals.narrate(symbol, signals),
                "value": value,
            }
        )

    return {
        "base_currency": base,
        "positions": rows,
        "summary": technicals.aggregate(rows),
        "unconvertible": unconvertible,
    }



@router.get(
    "/quarterly",
    response_model=QuarterlyOut,
    summary="Bir enstrümanın çeyreklik gelir tablosu serisi",
)
def get_quarterly(
    symbol: str = Query(..., min_length=1),
    limit: int = Query(default=8, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """
    Çeyrek çeyrek gelir, net kâr, vergi öncesi kâr ve faaliyet gideri.

    `/fundamentals` bir ANLIK GÖRÜNTÜ: alan başına tek güncel değer, geçmiş
    yok. Bu uç seriyi veriyor ve "son çeyrek kârı önceki çeyreğe göre" gibi
    bir cümleyi ilk kez mümkün kılan şey bu.

    BİTİŞİKLİK YANITTA. Sağlayıcının dönemleri ardışık gelmiyor -- ölçüldü,
    40 hissenin 3'ünde 2025Q3 gelir tablosunda hiç yok. "Son iki satırı al"
    diyen bir tüketici o hisselerde 2025Q2 ile 2025Q4'ü kıyaslar ve bunu
    söylemez; bu yüzden kural sunucuda hesaplanıp bayrak olarak gönderiliyor.

    Verisi olmayan enstrüman 404 DEĞİL, boş bir seri döndürür: "bu şirket için
    çeyreklik veri yok" bir cevaptır ve ölçülen kapsamada evrenin ~%15'i için
    doğru cevap odur.
    """
    found = market_service.quarterly_for(db, symbol, limit=limit)
    if found is None:
        product = market_service.resolve_symbol(db, symbol)
        return {
            "symbol": product.symbol if product else symbol.upper(),
            "name": (product.name if product else symbol.upper()) or symbol.upper(),
            "currency": (product.currency_code if product else "TRY") or "TRY",
            "periods": [],
        }
    return found


@router.post(
    "/quarterly/ingest",
    response_model=IngestResult,
    summary="Çeyreklik finansalları yükle (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
def ingest_quarterly(request: QuarterlyIngestRequest, db: Session = Depends(get_db)):
    """
    Çeyreklik satırları yazar; aynı dönem güncellenir, ikinci satır açılmaz.

    Sağlayıcı yayımlanmış bir çeyreği sonradan düzeltebiliyor ve iki sürümü
    yan yana saklamak, hangisinin doğru olduğunu söyleyemeyen bir seri
    bırakırdı.
    """
    written = market_service.upsert_quarterly(
        db, [item.model_dump() for item in request.items]
    )
    log.info("ingested %d quarterly rows of %d offered", written, len(request.items))
    return {"quotes_written": 0, "candles_written": 0, "news_written": 0,
            "quarterly_written": written}

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
    "/news/known-ids",
    summary="Kayıtlı bildirim numaraları (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
def known_news_ids(
    source: str = Query(..., min_length=2, max_length=40),
    db: Session = Depends(get_db),
):
    """`ingestor`'ın "bunlardan hangileri bende zaten var" diye sorduğu uç.

    KAP listesi her koşuda iki bin bildirim döndürüyor ve her birinin gövdesi
    ayrı bir sayfada. Sormadan çekmek, aynı iki bin sayfayı on beş dakikada
    bir yeniden istemek olurdu. `candles/coverage` ile aynı desen ve aynı
    sebep: kaynağa neyi zaten aldığımızı sormak yerine ona söylemek.

    Numara URL'den okunuyor, ayrı bir sütundan değil -- bildirimin adresi
    `.../Bildirim/1656735` ve numara zaten orada. Bunun için şema büyütmek,
    aynı bilgiyi ikinci kez saklamak olurdu.
    """
    return {"source": source, "ids": service.known_news_ids(db, source)}


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


def _notify_holders(db: Session, fresh: list[dict]) -> int:
    """Yeni gelen bir haber, o hisseyi TUTAN kullanıcılara bildirilir.

    Yalnızca gerçekten eklenen haberler için: `upsert_news` içerik hash'inde
    tekilleştiriyor ve zaten duran bir haberi yeniden bildirmek, akışı otuz
    saniyede bir tekrar eden bir gürültüye çevirirdi.

    Bir haber kullanıcının BİRDEN ÇOK hissesine dokunuyorsa yine TEK bildirim
    yazılıyor: aynı yazıyı üç kez göstermek, üç ayrı haber varmış gibi
    okunurdu.

    İki modülü burada birleştirmenin sebebi: pozisyonların sorgusu onları
    sahiplenen modülde (`market_service.holders_of`), satırın yazılması
    bildirim modülünde, ve hiçbiri diğerinin tablosunu okumuyor.

    Bildirim yazamamak haber yüklemesini DÜŞÜRMEZ: haber sistemin verisi,
    bildirim onun üstüne konan bir kolaylık.
    """
    if not fresh:
        return 0
    symbols = sorted({s for item in fresh for s in item["symbols"]})
    holders = market_service.holders_of(db, symbols)
    if not holders:
        return 0

    per_user: dict[str, list[dict]] = {}
    for item in fresh:
        for user_id in {u for s in item["symbols"] for u in holders.get(s, set())}:
            per_user.setdefault(user_id, []).append(item)

    written = 0
    for user_id, items in per_user.items():
        capped = items[: notification_service.MAX_PER_USER_PER_BATCH]
        if len(items) > len(capped):
            log.info(
                "notification batch capped for one user: %d -> %d",
                len(items), len(capped),
            )
        for item in capped:
            held = sorted(
                s for s in item["symbols"] if user_id in holders.get(s, set())
            )
            written += notification_service.create_many(
                db, [user_id],
                title="Portföyünüzle ilgili haber",
                description=f"{', '.join(held)}: {item['title']}"[:255],
                type="INFO",
                link_url="/analiz/genel",
            )
    return written


@router.post(
    "/news/ingest",
    response_model=IngestResult,
    summary="Haber yükle (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
def ingest_news(request: NewsIngestRequest, db: Session = Depends(get_db)):
    written, symbols, fresh = service.upsert_news(
        db, [item.model_dump() for item in request.items]
    )
    # `upsert_news` kendi commit'ini attı; bildirimler ayrı bir transaction.
    # Bildirimi yazamamak haberi kaybetmemeli, o yüzden bu sırayla.
    notified = _notify_holders(db, fresh)
    if notified:
        db.commit()
    log.info(
        "ingested %d new news items of %d offered, %d symbol-tagged, "
        "%d notifications",
        written, len(request.items), len(symbols), notified,
    )
    # Semboller geri veriliyor: çözümleme evrenin bulunduğu yerde yapılıyor
    # ve `ingestor` aynı haberi RAG'a da yazıyor. Sonucu geri vermezsek
    # korpustaki kopya etiketsiz kalır.
    return {"quotes_written": 0, "candles_written": 0, "news_written": written,
            "news_symbols": symbols}


@router.get(
    "/news/coverage",
    summary="Kaynak başına haber kapsaması (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
def news_coverage(db: Session = Depends(get_db)):
    """`ingestor`'ın "nereden devam edeyim" sorusu.

    `candles/coverage` ile aynı desen. KAP bildirim numarası monoton
    olduğu için en yüksek numara, bir tarihten daha kesin bir su seviyesi.
    """
    return service.news_coverage(db)


@router.get(
    "/news/archive",
    summary="Saklanan bildirimleri sayfa sayfa oku (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
def news_archive(
    source: str = Query(default="KAP", max_length=120),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """`ingestor`'ın "hangi bildirimin gövdesi hâlâ eksik" taramasını
    beslediği uç.

    Panoya 28.984 bildirim düştü ama derlemde yalnızca yeni gelenlerin
    gövdesi var: gövde çekimi bildirim başına bir istek ve tur başına
    bütçeli. Bu uç, arşivin geri kalanını kapatan işin girdisi.
    """
    rows = service.news_archive(db, source, limit, offset)
    return {
        "items": [
            {
                "content_hash": row.content_hash,
                "title": row.title,
                "url": row.url,
                "related_symbols": list(row.related_symbols or []),
                "published_at": row.published_at,
            }
            for row in rows
        ]
    }


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


@router.post(
    "/sessions",
    summary="Açık piyasaları bildir (servisler arası)",
    dependencies=[Depends(require_service_token)],
)
def record_sessions(request: SessionStateRequest, db: Session = Depends(get_db)):
    """
    Hangi piyasaların şu an işlem gördüğünü kaydeder.

    Saatler burada DEĞİL, `ingestor`'da -- ve orada kalıyor. Backend'e KURAL
    değil OLGU geliyor: ikinci bir saat listesi tutmak, bu depoda defalarca
    ayrışan türden bir şey olurdu.

    Bu olmadan backend, eski bir fiyatın "piyasa kapalı" mı yoksa "veri akışı
    durdu" mu olduğunu ayırt edemiyordu ve kullanıcıya sebebi söylemeyen bir
    cümle kurmak zorundaydı.
    """
    written = market_service.record_sessions(db, request.open)
    log.info("session state: %d markets, open=%s", written, sorted(request.open))
    return {"markets": written}


# ── Fonlar (TEFAS) ──────────────────────────────────────────────────────────


@router.get("/funds", response_model=FundListOut, summary="Fon listesi (TEFAS)")
def list_funds(
    founder: Optional[str] = Query(default=None, max_length=200),
    umbrella: Optional[str] = Query(default=None, max_length=120),
    fund_type: Optional[str] = Query(default=None, max_length=8),
    q: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=funds_service.MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Süzülmüş fon listesi.

    Süzgeçler SUNUCUDA: evren 2.602 fon ve hepsini tarayıcıya gönderip orada
    süzmek, her açılışta birkaç yüz kilobayt ve süzgeç mantığının ikinci bir
    kopyası demekti.

    Getiriler NAV serisinden HESAPLANIYOR, saklanmıyor -- aynı sayının iki
    yerde yaşaması, serinin güncellendiği ama yüzdenin güncellenmediği bir
    aralık bırakırdı.
    """
    rows = funds_service.list_funds(
        db, founder=founder, umbrella=umbrella, fund_type=fund_type,
        search=q, limit=limit, offset=offset,
    )
    facets = funds_service.facets(db)
    return {
        "items": [_fund_row(db, row) for row in rows],
        "founders": facets["founders"],
        "umbrellas": facets["umbrellas"],
        "total": len(rows),
    }


@router.get("/funds/{code}", response_model=FundOut, summary="Tek fon")
def get_fund(code: str, db: Session = Depends(get_db)):
    rows = funds_service.list_funds(db, search=code, limit=funds_service.MAX_LIMIT)
    match = next((row for row in rows if row.code == code.strip().upper()), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Fon bulunamadı.")
    return _fund_row(db, match)


@router.get(
    "/funds/{code}/prices",
    response_model=FundSeriesOut,
    summary="Fonun NAV serisi",
)
def get_fund_prices(
    code: str,
    limit: int = Query(default=400, ge=2, le=2000),
    db: Session = Depends(get_db),
):
    """Fon mum grafiğinin okuduğu seri.

    Bilinmeyen kod boş seri döndürüyor, hata değil: "bu fonun geçmişi yok"
    bir cevaptır ve grafik onu boş çizebilir -- `/market/candles` ile aynı
    duruş.
    """
    series = funds_service.price_series(db, code, limit=limit)
    return {
        "code": code.strip().upper(),
        "currency": "TRY",
        "points": [{"date": row.as_of, "price": float(row.price)} for row in series],
    }


@router.get(
    "/funds/{code}/candles",
    response_model=FundCandleSeriesOut,
    summary="Fonun mum serisi",
)
def get_fund_candles(
    code: str,
    window: str = Query(default="3A"),
    db: Session = Depends(get_db),
):
    """Kovalanmış OHLC.

    Fon günde TEK fiyat yayımlıyor, dolayısıyla GÜNLÜK mum diye bir şey
    yok: açılış/yüksek/düşük/kapanış aynı sayı olurdu. Kova genişliği
    yanıtta taşınıyor ki arayüz "haftalık mum" diye yazabilsin -- kullanıcı
    baktığı çubuğun bir günü mü bir haftayı mı özetlediğini bilmeli.
    """
    if window not in funds_service.CANDLE_RANGES:
        raise HTTPException(status_code=422, detail=f"Bilinmeyen aralık: {window}")
    bucket, _ = funds_service.CANDLE_RANGES[window]
    return {
        "code": code.strip().upper(),
        "currency": "TRY",
        "bucket": bucket,
        "candles": funds_service.candles(db, code, window),
    }


@router.post("/funds/ingest", summary="Fon verisi yaz (servis işi)")
def ingest_funds(
    request: FundIngestRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_service_token),
):
    """Toplayıcının yazdığı yer. `news/ingest` ile aynı desen."""
    written = funds_service.upsert_funds(db, request.funds)
    prices = funds_service.upsert_prices(db, request.prices)
    # İşlem gören fonların kotasyonu da tazelensin: portföy değeri ve
    # bekleyen fon emirleri `market_quotes`tan okuyor, `market.funds`tan
    # değil.
    quotes = funds_service.sync_quotes(db)
    db.commit()
    return {"funds_written": written, "prices_written": prices, "quotes_written": quotes}


@router.get("/funds/meta/coverage", summary="Eksik fon verisi (servis işi)")
def funds_coverage(
    db: Session = Depends(get_db),
    _: None = Depends(require_service_token),
):
    """Toplayıcı her turda neyi çekeceğini buradan öğreniyor.

    Şemsiye türü ve NAV serisi fon BAŞINA birer istek; hangilerinin eksik
    olduğunu bilmeden her tur baştan başlardı.
    """
    return funds_service.coverage(db)


def _fund_row(db: Session, row) -> dict:
    """Bir fon satırı + serisinden türetilen getiriler."""
    series = funds_service.price_series(db, row.code)
    return {
        "code": row.code,
        "name": row.title,
        "founder": row.founder,
        "umbrella": row.umbrella,
        "fundType": row.fund_type,
        "price": float(row.price) if row.price is not None else None,
        "investorCount": row.investors,
        "size": float(row.size) if row.size is not None else None,
        "asOf": row.as_of,
        "categoryRank": row.category_rank,
        "categorySize": row.category_size,
        "shares": float(row.shares) if row.shares is not None else None,
        "returns": funds_service.returns_for(series),
    }
