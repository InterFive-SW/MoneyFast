import json
import re
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


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


SocialSourceType = Literal[
    "official_company",
    "official_disclosure",
    "disclosure_aggregator",
    "news_agency",
    "financial_media",
    "analyst",
]
SocialPostKind = Literal["original", "reply", "repost", "quote"]
SocialVerificationStatus = Literal[
    "unverified",
    "corroborated",
    "officially_verified",
    "contradicted",
]

_X_ID = re.compile(r"^[0-9]{1,64}$")
_X_HANDLE = re.compile(r"^[a-z0-9_]{1,15}$")
MAX_SOCIAL_RAW_METADATA_BYTES = 16_384
SOCIAL_INGEST_MAX_ACCOUNTS = 100
SOCIAL_INGEST_MAX_POSTS = 1_000
_FORBIDDEN_METADATA_KEYS = {
    "authorization",
    "bearer_token",
    "access_token",
    "api_key",
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(timezone.utc)


def _contains_credential_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).casefold() in _FORBIDDEN_METADATA_KEYS
            or _contains_credential_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_credential_key(item) for item in value)
    return False


class SocialAccountIn(BaseModel):
    platform: Literal["x"] = "x"
    external_account_id: str
    handle: str
    display_name: Optional[str] = Field(default=None, max_length=255)
    source_type: SocialSourceType
    trust_score: float = Field(ge=0.0, le=1.0)
    is_active: bool = True

    @field_validator("external_account_id")
    @classmethod
    def valid_external_account_id(cls, value: str) -> str:
        value = value.strip()
        if not _X_ID.fullmatch(value):
            raise ValueError("external_account_id must be a numeric X user id")
        return value

    @field_validator("handle")
    @classmethod
    def normalized_handle(cls, value: str) -> str:
        value = value.strip().removeprefix("@").lower()
        if not _X_HANDLE.fullmatch(value):
            raise ValueError("handle must be a valid X handle")
        return value


class SocialPostIn(BaseModel):
    platform: Literal["x"] = "x"
    account_external_id: str
    external_post_id: str
    content_text: str = Field(max_length=20_000)
    post_url: str = Field(max_length=1_024)
    language: Optional[str] = Field(default=None, max_length=10)
    published_at: datetime
    collected_at: datetime
    post_kind: SocialPostKind
    referenced_external_post_id: Optional[str] = None
    conversation_id: Optional[str] = Field(default=None, max_length=64)
    is_tombstoned: bool = False
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    underlying_source_url: Optional[str] = Field(default=None, max_length=2_048)
    instrument_references: List[str] = Field(default_factory=list, max_length=20)

    @field_validator(
        "account_external_id",
        "external_post_id",
        "referenced_external_post_id",
    )
    @classmethod
    def valid_x_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not _X_ID.fullmatch(value):
            raise ValueError("X ids must be numeric")
        return value

    @field_validator("published_at", "collected_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("instrument_references")
    @classmethod
    def bounded_instrument_references(cls, value: List[str]) -> List[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if any(len(item) > 255 for item in cleaned):
            raise ValueError("instrument references must be at most 255 characters")
        return list(dict.fromkeys(cleaned))

    @field_validator("raw_metadata")
    @classmethod
    def bounded_public_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
        except (TypeError, ValueError) as exc:
            raise ValueError("raw_metadata must be JSON serializable") from exc
        if len(encoded) > MAX_SOCIAL_RAW_METADATA_BYTES:
            raise ValueError("raw_metadata is too large")
        if _contains_credential_key(value):
            raise ValueError("raw_metadata contains a credential-like field")
        return value

    @model_validator(mode="after")
    def active_posts_have_content(self):
        if not self.is_tombstoned and not self.content_text.strip():
            raise ValueError("active social posts require non-empty content")
        return self


class SocialIngestRequest(BaseModel):
    accounts: List[SocialAccountIn] = Field(
        default_factory=list, max_length=SOCIAL_INGEST_MAX_ACCOUNTS
    )
    posts: List[SocialPostIn] = Field(
        default_factory=list, max_length=SOCIAL_INGEST_MAX_POSTS
    )

    @model_validator(mode="after")
    def unique_external_ids(self):
        account_keys = [
            (item.platform, item.external_account_id) for item in self.accounts
        ]
        account_handles = [(item.platform, item.handle) for item in self.accounts]
        post_keys = [(item.platform, item.external_post_id) for item in self.posts]
        if len(account_keys) != len(set(account_keys)):
            raise ValueError("duplicate account external ids in one batch")
        if len(account_handles) != len(set(account_handles)):
            raise ValueError("duplicate normalized account handles in one batch")
        if len(post_keys) != len(set(post_keys)):
            raise ValueError("duplicate post external ids in one batch")
        return self


class UnresolvedSocialReference(BaseModel):
    external_post_id: str
    reference: str
    candidates: List[str] = Field(default_factory=list)


class SocialIngestResult(BaseModel):
    accounts_inserted: int = 0
    accounts_updated: int = 0
    accounts_duplicate: int = 0
    posts_inserted: int = 0
    posts_updated: int = 0
    posts_duplicate: int = 0
    posts_tombstoned: int = 0
    instruments_matched: int = 0
    instruments_unresolved: int = 0
    instrument_links_removed: int = 0
    unresolved: List[UnresolvedSocialReference] = Field(default_factory=list)


class SocialSignalOut(BaseModel):
    platform: str
    handle: str
    displayName: Optional[str] = None
    sourceType: SocialSourceType
    trustScore: float
    verificationStatus: SocialVerificationStatus
    publishedAt: datetime
    collectedAt: datetime
    text: str
    postUrl: str
    underlyingSourceUrl: Optional[str] = None
    underlyingSourceType: Optional[str] = None
    matchedSymbols: List[str] = Field(default_factory=list)
    postKind: SocialPostKind


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
