from datetime import date, datetime

from pydantic import BaseModel, Field
from typing import List, Literal, Optional

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


class PortfolioNewsSymbol(BaseModel):
    """Portföydeki bir sembol ve o pencerede ona dokunan haber sayısı."""
    symbol: str
    name: str
    count: int


class PortfolioNewsItem(NewsItem):
    """Akış öğesi + haberin hangi pozisyonlara dokunduğu.

    `relatedSymbols` haberin TÜM etiketlerini taşır; `heldSymbols` bunların
    kullanıcının gerçekten tuttuğu alt kümesi. İkisi ayrı, çünkü "BIST 100
    değer kaybetti" haberi dört şirketi anıyor olabilir ve kullanıcı bunlardan
    yalnızca birine sahiptir -- panelde hangisi yüzünden listelendiği
    okunabilir olmalı.
    """
    publishedAt: datetime
    heldSymbols: List[str]


class PortfolioNewsOut(BaseModel):
    """Portföye dokunan haberler paneli.

    Haber olmadığında da dönen bir gövde: `symbols` doludur, `items` boştur.
    Sessizce kaybolan bir panel, veri yokluğunu özellik yokluğu gibi gösterir.
    """
    symbols: List[PortfolioNewsSymbol]
    items: List[PortfolioNewsItem]
    #: Sayıların ve başlıkların okunduğu pencere. Panel "son 30 günde" diye
    #: yazabilsin diye dönüyor; sabiti arayüzde ikinci kez yazmak, birinin
    #: değişip diğerinin kalmasına açık olurdu.
    windowDays: int



# ---------------------------------------------------------------------------
# Service-to-service ingest contracts
#
# snake_case here, unlike the camelCase read models above: these are consumed
# by the `ingestor` service, not by the React frontend, and the two change for
# different reasons.
# ---------------------------------------------------------------------------
# `datetime` is imported at the top of the file: the read models above now
# carry a timestamp too, and a second import here would only be a name the
# linter reports as redefined.
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


class QuarterlyIn(BaseModel):
    """Bir enstrümanın bir çeyreği.

    Her sayısal alan Optional ve öyle kalıyor. Ölçüldü: 34 hissenin 16'sında
    serinin bir yerinde eksik değer var ve sıfıra çevirmek "o çeyrek
    raporlandı, kâr sıfır çıktı" demek olurdu.
    """
    symbol: str
    period_end: date
    total_revenue: Optional[int] = None
    net_income: Optional[int] = None
    pretax_income: Optional[int] = None
    operating_expense: Optional[int] = None


class QuarterlyIngestRequest(BaseModel):
    items: List[QuarterlyIn] = Field(default_factory=list)


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

    # 0027: gelir tablosu ve kârlılık. Pydantic tanımadığı alanı SESSİZCE
    # düşürür, dolayısıyla burada listelenmeyen bir alan ingestor tarafından
    # gönderilse bile veritabanına hiç ulaşmaz -- şirket adının bir dönem
    # başına gelen tam olarak buydu.
    total_revenue: Optional[int] = None
    revenue_growth: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    ebitda_margin: Optional[float] = None
    profit_margin: Optional[float] = None
    return_on_equity: Optional[float] = None
    return_on_assets: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    total_debt: Optional[int] = None
    total_cash: Optional[int] = None
    free_cash_flow: Optional[int] = None
    operating_cash_flow: Optional[int] = None
    enterprise_value: Optional[int] = None
    beta: Optional[float] = None
    trailing_eps: Optional[float] = None
    forward_eps: Optional[float] = None
    forward_pe: Optional[float] = None
    earnings_growth: Optional[float] = None
    payout_ratio: Optional[float] = None
    dividend_rate: Optional[float] = None
    recommendation_key: Optional[str] = None
    analyst_count: Optional[int] = None
    target_mean_price: Optional[float] = None
    ex_dividend_date: Optional[datetime] = None
    earnings_date: Optional[datetime] = None


class FundamentalsIngestRequest(BaseModel):
    items: List[FundamentalsIn] = Field(default_factory=list)


class IngestResult(BaseModel):
    quotes_written: int = 0
    candles_written: int = 0
    news_written: int = 0
    fundamentals_written: int = 0
    quarterly_written: int = 0
    #: Haber yüklemesinde çözülen semboller, `content_hash` -> semboller.
    #: `ingestor` bunu RAG'a yazarken kullanıyor: çözümleme evrenin bulunduğu
    #: yerde, yani BURADA yapılıyor ve sonucu geri vermezsek korpustaki kopya
    #: etiketsiz kalıyor -- ölçüldü, 1.970 RSS belgesinin sıfırında ticker
    #: vardı ve ajanın `tickers` filtresi onlarda hiç çalışmıyordu.
    news_symbols: dict[str, List[str]] = {}


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


class TechnicalSignals(BaseModel):
    """Hesaplanan göstergeler.

    Her alan `Optional`: yeterli bar olmadığında değer YOKTUR. 60 barı olan
    bir enstrümanda `sma_200` boştur, elde olan barlarla hesaplanmış bir
    yaklaşık değil -- "200 günlük ortalama" adını taşıyıp 60 günü ölçen bir
    sayı, okuyanı yanıltır.
    """

    observations: int = 0
    last_close: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    pct_from_sma_20: Optional[float] = None
    pct_from_sma_50: Optional[float] = None
    pct_from_sma_200: Optional[float] = None
    rsi_14: Optional[float] = None
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None
    week52_position_pct: Optional[float] = None
    up_days_recent: Optional[int] = None
    recent_window: Optional[int] = None
    volume_vs_average: Optional[float] = None
    annualised_volatility: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    #: UPTREND / DOWNTREND / SIDEWAYS / UNKNOWN
    trend: str = "UNKNOWN"


class TechnicalSignalsOut(BaseModel):
    symbol: str
    currency: str = "TRY"
    signals: TechnicalSignals
    #: Kullanıcıya gösterilecek Türkçe cümle, tam hâliyle. Yeterli geçmiş
    #: yoksa None -- boş bir cümle üretmek yerine hiç üretilmiyor.
    narrative: Optional[str] = None


class PortfolioTechnicalRow(TechnicalSignalsOut):
    """Bir pozisyonun teknik durumu, portföydeki yeriyle birlikte.

    `TechnicalSignalsOut`'u genişletiyor: tek hisse sayfasıyla portföy paneli
    aynı alanları okusun ki ikisi aynı hisse için farklı bir eğilim
    gösteremesin.
    """
    name: str
    #: Taban para birimine çevrilmiş pozisyon değeri. Kuru olmayan bir
    #: pozisyonda None -- 1.0 varsayılmaz, o pozisyon ağırlık hesabına
    #: girmez ve `unconvertible` içinde adı geçer.
    value: Optional[float] = None


class PortfolioTechnicalSummary(BaseModel):
    """Toplulaştırma. Sayı ve değer AYRI, çünkü zıt yönü gösterebilirler."""
    position_count: int
    measured_count: int
    unmeasured_symbols: List[str]
    by_trend: dict[str, int]
    below_sma_50: int
    above_sma_50: int
    weight_below_sma_50: Optional[float] = None
    #: Ekranın ve sohbetin AYNI cümlesi. İki yüzeyin aynı ölçümü farklı
    #: anlatması, kullanıcının hangisine güveneceğini bilememesi demekti.
    statement: Optional[str] = None


class PortfolioTechnicalOut(BaseModel):
    base_currency: str = "TRY"
    positions: List[PortfolioTechnicalRow]
    summary: PortfolioTechnicalSummary
    #: Para birimi çevrilemediği için ağırlık hesabına girmeyen pozisyonlar.
    #: Sessizce düşürmek, portföyün bir kısmını yok saymak olurdu.
    unconvertible: List[str] = []

class QuarterOut(BaseModel):
    """Bir çeyrek. Etiket türetiliyor, saklanmıyor."""
    period_end: date
    #: `2026Q2`. `period_end`'den türetiliyor; iki kez saklamak ikisinin
    #: ayrışabileceği bir yer açardı.
    label: str
    total_revenue: Optional[int] = None
    net_income: Optional[int] = None
    pretax_income: Optional[int] = None
    operating_expense: Optional[int] = None


class QuarterlyOut(BaseModel):
    """Bir enstrümanın çeyreklik serisi, en yeniden eskiye.

    İki bayrak sunucuda hesaplanıyor, tüketende değil. Ölçüldü: sağlayıcının
    dönemleri ardışık gelmiyor -- 40 hissenin 3'ünde 2025Q3 gelir tablosunda
    hiç yok. "Son iki satırı al" diyen bir karşılaştırma o hisselerde 2025Q2
    ile 2025Q4'ü kıyaslar ve bunu söylemez.
    """
    symbol: str
    name: str
    currency: str = "TRY"
    periods: List[QuarterOut] = []
    #: En yeni dönemin bir öncekiyle BİTİŞİK olup olmadığı. False ise
    #: çeyreklik karşılaştırma yapılamaz.
    previous_is_adjacent: bool = False
    #: Geçen yılın aynı çeyreği elde mi -- tam dört çeyrek geride.
    year_ago_available: bool = False

class FundamentalsOut(BaseModel):
    """Bir enstrümanın saklanan tüm temel verisi.

    `/market/instruments`'ten AYRI: o, dondurulmuş v2.2 sözleşmesi ve bir
    LİSTE için "bu ne ediyor" sorusunu yanıtlıyor. Bunlar tek bir şirket
    hakkında otuz küsur alan ve tarama ekranlarının çoğu hiçbirine
    bakmıyor -- teknik göstergeleri kendi uç noktasına koyan gerekçenin
    aynısı.

    Her alan Optional ve öyle kalıyor. Bankanın brüt marjı YOKTUR; onu 0
    olarak vermek, şirketin hiç sahip olmadığı bir olguyu bildirmek olur.
    """

    symbol: str
    name: Optional[str] = None
    currency: str = "TRY"
    updated_at: Optional[datetime] = None

    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    market_cap: Optional[int] = None
    dividend_yield: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    week52_high: Optional[float] = None
    week52_low: Optional[float] = None

    total_revenue: Optional[int] = None
    revenue_growth: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    ebitda_margin: Optional[float] = None
    profit_margin: Optional[float] = None
    return_on_equity: Optional[float] = None
    return_on_assets: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    total_debt: Optional[int] = None
    total_cash: Optional[int] = None
    free_cash_flow: Optional[int] = None
    operating_cash_flow: Optional[int] = None
    enterprise_value: Optional[int] = None
    beta: Optional[float] = None
    trailing_eps: Optional[float] = None
    forward_eps: Optional[float] = None
    forward_pe: Optional[float] = None
    earnings_growth: Optional[float] = None
    payout_ratio: Optional[float] = None
    dividend_rate: Optional[float] = None

    #: Analist konsensüsü: BAŞKASININ değerlendirmesi. Aktarılabilir bir olgu,
    #: ürünün kendi görüşü değil.
    recommendation_key: Optional[str] = None
    analyst_count: Optional[int] = None
    target_mean_price: Optional[float] = None

    ex_dividend_date: Optional[datetime] = None
    earnings_date: Optional[datetime] = None


class AnalystRow(BaseModel):
    """Bir enstrüman için analist konsensüsü.

    BAŞKASININ değerlendirmesi. "16 analistin ortalama hedefi 95,39 TL"
    aktarılabilir bir olgudur; ürünün kendi görüşü değildir.
    """

    symbol: str
    name: Optional[str] = None
    currency: str = "TRY"
    recommendation: str
    analyst_count: int
    target_mean_price: Optional[float] = None


class DividendRow(BaseModel):
    symbol: str
    name: Optional[str] = None
    currency: str = "TRY"
    dividend_yield: Optional[float] = None
    dividend_rate: Optional[float] = None
    payout_ratio: Optional[float] = None
    ex_dividend_date: Optional[datetime] = None


class EarningsRow(BaseModel):
    symbol: str
    name: Optional[str] = None
    currency: str = "TRY"
    earnings_date: datetime


class MarketCalendarOut(BaseModel):
    """"Analizler" ekranının üç listesi, tek çağrıda."""

    analysts: List[AnalystRow] = Field(default_factory=list)
    dividends: List[DividendRow] = Field(default_factory=list)
    earnings: List[EarningsRow] = Field(default_factory=list)


class SessionStateRequest(BaseModel):
    """Hangi piyasalar ŞU AN açık.

    Liste TAM: burada olmayan her piyasa kapalı sayılır. Kısmi bir liste,
    bildirilmeyen piyasanın durumunu belirsiz bırakırdı ve belirsizlik
    "kapalı" diye okunurdu.
    """

    open: List[str] = Field(default_factory=list)


# ── Fonlar (TEFAS) ──────────────────────────────────────────────────────────


class FundReturnsOut(BaseModel):
    """Pencere başına yüzde getiri.

    Her alan `Optional` ve bu kasıtlı: `null` "bu fonun o kadar geçmişi yok"
    demek, sıfır ise "o dönemde hiç kazandırmadı". Arayüz ilkini `NA` diye
    yazıyor ve ikisini aynı sayıya indirmek, olmayan bir ölçümü ölçüm gibi
    göstermek olurdu.
    """

    daily: Optional[float] = None
    monthly: Optional[float] = None
    threeMonth: Optional[float] = None
    yearly: Optional[float] = None
    threeYear: Optional[float] = None
    fiveYear: Optional[float] = None


class FundOut(BaseModel):
    """Listede bir fon.

    Yönetim ücreti, stopaj ve risk değeri YOK: TEFAS API'si bu alanları
    döndürmüyor (HAR kaydındaki 85 alanın hepsi tarandı) ve döndürmediği bir
    alan için `null` taşımak, bir gün dolacakmış gibi duran bir söz olurdu.
    """

    code: str
    name: str
    founder: Optional[str] = None
    umbrella: Optional[str] = None
    fundType: Optional[str] = None
    price: Optional[float] = None
    investorCount: Optional[int] = None
    size: Optional[float] = None
    #: Fiyatın ait olduğu GÜN. Fon fiyatı günlüktür.
    asOf: Optional[date] = None
    #: TEFAS'ın kategori içi sırası: "86 fon içinde 71." Sıra, getirinin
    #: tek başına söyleyemediği şeyi söylüyor.
    categoryRank: Optional[int] = None
    categorySize: Optional[int] = None
    #: Kategorinin ortalama getirisi -- fonun kendi getirisinin ölçüldüğü yer.
    #: Tedavüldeki pay sayısı.
    shares: Optional[float] = None
    returns: FundReturnsOut = Field(default_factory=FundReturnsOut)


class FundListOut(BaseModel):
    items: List[FundOut] = Field(default_factory=list)
    #: Süzgeç açılır listeleri veriden geliyor, elle yazılmış değil.
    founders: List[str] = Field(default_factory=list)
    umbrellas: List[str] = Field(default_factory=list)
    total: int = 0


class FundPricePointOut(BaseModel):
    date: date
    price: float


class FundSeriesOut(BaseModel):
    code: str
    #: TEFAS fonları TL cinsinden. Sabit değil, alan olarak taşınıyor: bir
    #: fiyat para birimi olmadan taşınmaz, bu deponun kuralı.
    currency: str = "TRY"
    points: List[FundPricePointOut] = Field(default_factory=list)


class FundCandleOut(BaseModel):
    """Kovalanmış bir mum.

    Hacim YOK: bir fonun günlük işlem hacmi TEFAS'ta yayımlanmıyor ve
    sıfır yazmak "hiç kimse almadı" demek olurdu.
    """

    date: date
    open: float
    high: float
    low: float
    close: float


class FundCandleSeriesOut(BaseModel):
    code: str
    currency: str = "TRY"
    #: `week` ya da `month` -- arayüz "haftalık mum" diye yazabilsin diye.
    #: Fon günde tek fiyat yayımlıyor, dolayısıyla günlük mum diye bir şey
    #: yok ve kullanıcının kovanın genişliğini bilmesi gerekiyor.
    bucket: str
    candles: List[FundCandleOut] = Field(default_factory=list)


class FundIngestRequest(BaseModel):
    """Toplayıcının yazdığı gövde."""

    funds: List[dict] = Field(default_factory=list)
    prices: List[dict] = Field(default_factory=list)
