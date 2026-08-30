from pydantic import BaseModel
from typing import List, Literal

class MarketTicker(BaseModel):
    """
    Piyasa verisi (hisse, döviz, kripto vb.) anlık durum modeli.
    """
    symbol: str
    #: The instrument's own currency — XAUUSD is dollars, XU100 is index points.
    currency: str = "TRY"
    price: float
    change: float
    changePercent: float

class NewsItem(BaseModel):
    """
    Finansal haber akışı öğesi.
    """
    id: str
    source: str
    title: str
    url: str
    time: str
    sentiment: Literal["positive", "negative", "neutral"]
    relatedSymbols: List[str]


# ---------------------------------------------------------------------------
# Service-to-service ingest contracts
#
# snake_case here, unlike the camelCase read models above: these are consumed
# by the `ingestor` service, not by the React frontend, and the two change for
# different reasons.
# ---------------------------------------------------------------------------
from datetime import datetime  # noqa: E402
from typing import Optional  # noqa: E402

from pydantic import Field  # noqa: E402


class QuoteIn(BaseModel):
    symbol: str
    price: float
    change_amount: Optional[float] = None
    change_percent: Optional[float] = None
    previous_close: Optional[float] = None
    volume: Optional[int] = None
    #: When the price was true at the exchange, NOT when it was fetched. The
    #: gap between the two is the delay the AI contract obliges the assistant
    #: to disclose, so the provider's own timestamp is required.
    market_timestamp: datetime
    source: str = "yfinance"


class CandleIn(BaseModel):
    symbol: str
    interval: str = "1d"
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[int] = None
    source: str = "yfinance"


class QuoteIngestRequest(BaseModel):
    quotes: List[QuoteIn] = Field(default_factory=list)
    candles: List[CandleIn] = Field(default_factory=list)


class NewsItemIn(BaseModel):
    content_hash: str = Field(min_length=64, max_length=64)
    title: str
    summary: Optional[str] = None
    source: str
    url: Optional[str] = None
    language: str = "tr"
    related_symbols: List[str] = Field(default_factory=list)
    published_at: datetime


class NewsIngestRequest(BaseModel):
    items: List[NewsItemIn] = Field(default_factory=list)


class FundamentalsIn(BaseModel):
    """One instrument's ratios.

    Every field is Optional and none is ever defaulted. Provider coverage is
    partial, and a missing P/E written as 0 would make a company with no
    published earnings screen as the cheapest name on the list.
    """

    symbol: str
    #: The provider's company name, used to backfill instruments stored with
    #: name = ticker. Without this field Pydantic dropped it at the boundary,
    #: so the ingestor sent it and the backfill never saw it.
    name: Optional[str] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    market_cap: Optional[int] = None
    dividend_yield: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None


class FundamentalsIngestRequest(BaseModel):
    items: List[FundamentalsIn] = Field(default_factory=list)


class IngestResult(BaseModel):
    quotes_written: int = 0
    candles_written: int = 0
    news_written: int = 0
    fundamentals_written: int = 0


class InstrumentOut(BaseModel):
    """One instrument for the screening endpoint and the market-data tool.

    Every fundamental is Optional and stays that way. Provider coverage is
    partial, and a missing P/E rendered as 0 would put a stock with no
    earnings data at the top of a "cheapest" list.
    """

    symbol: str
    name: str
    market: Optional[str] = None
    currency: str = "TRY"
    price: float
    change: Optional[float] = None
    change_percent: Optional[float] = None
    #: Son seansın işlem hacmi (adet). Veritabanında 94/94 satırda DOLUYDU ama
    #: hiçbir uç nokta dışarı vermiyordu, dolayısıyla sohbetteki "Günlük ciro"
    #: sütunu her zaman "veri yok" yazıyordu — eksik olan veri değil, alanın
    #: kendisiydi.
    volume: Optional[int] = None
    market_timestamp: datetime
    #: Fiyatı gözlemlediğimiz an. `market_timestamp` barın kendi damgası ve
    #: günlük barlarda seans açılışını gösterir; tazeliği ondan ölçmek güncel
    #: bir fiyatı 12 saat eski gibi raporlar.
    received_at: Optional[datetime] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    market_cap: Optional[int] = None
    dividend_yield: Optional[float] = None
    sector: Optional[str] = None
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None


class UnresolvedSymbol(BaseModel):
    """A query that matched no single instrument, and the near misses.

    `candidates` empty means nothing was close; non-empty means the caller
    should ask which one rather than reporting a dead end.
    """

    query: str
    candidates: List[str] = Field(default_factory=list)


class InstrumentListOut(BaseModel):
    instruments: List[InstrumentOut] = Field(default_factory=list)
    unresolved: List[UnresolvedSymbol] = Field(default_factory=list)


class CandleOut(BaseModel):
    """One daily bar. All four prices, because a chart needs more than closes."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    #: Yahoo does not always report it; missing stays missing rather than 0,
    #: which would draw as a day nobody traded.
    volume: Optional[int] = None


class CandleSeriesOut(BaseModel):
    symbol: str
    #: Currency the bars are priced in.
    currency: str = "TRY"
    interval: str = "1d"
    candles: List[CandleOut] = Field(default_factory=list)


class InstrumentSuggestion(BaseModel):
    """Arama kutusunun gösterdiği tek satır."""

    symbol: str
    name: Optional[str] = None
    market: Optional[str] = None
    currency: Optional[str] = None


class HeatmapTile(BaseModel):
    """Isı haritasında bir kutu."""

    symbol: str
    name: Optional[str] = None
    #: Kutunun ALANI bundan geliyor. Değeri bilinmeyen enstrüman haritaya
    #: girmiyor: varsayılan bir boyut, ona sahip olmadığı bir ağırlık verirdi.
    marketCap: float
    changePercent: float
    sector: str = "Bilinmiyor"
    price: float
    currency: str = "TRY"


class MarketHeatmapOut(BaseModel):
    items: List[HeatmapTile] = []
    #: Piyasa değeri ya da günlük değişimi olmadığı için çizilemeyen sayısı.
    #: Sessizce düşen kutular haritayı olduğundan küçük gösterir.
    missing: int = 0
