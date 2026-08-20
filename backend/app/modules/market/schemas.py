from pydantic import BaseModel
from typing import List, Literal

class MarketTicker(BaseModel):
    """
    Piyasa verisi (hisse, döviz, kripto vb.) anlık durum modeli.
    """
    symbol: str
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


class InstrumentListOut(BaseModel):
    instruments: List[InstrumentOut] = Field(default_factory=list)
