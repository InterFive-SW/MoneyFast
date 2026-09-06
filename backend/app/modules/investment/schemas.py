from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class InvestmentBreakdown(BaseModel):
    cashTRY: float
    stocksBIST: float
    stocksUS: float

class InvestmentBalance(BaseModel):
    totalTRY: float
    totalUSD: float
    breakdown: InvestmentBreakdown
    #: Bekleyen emirlerin tuttuğu nakit. Bakiyeden ZATEN düşülmüş; ayrıca
    #: bildiriliyor çünkü nedeni yazılmayan bir eksilme bir hataya benziyor.
    blockedTRY: float = 0.0

class Position(BaseModel):
    symbol: str
    price: float
    quantity: float
    avgCost: float
    totalValue: float
    dailyReturn: float
    dailyReturnPercent: float
    totalReturn: float
    totalReturnPercent: float
    #: The instrument's own currency. Dropped for a long time, which is why
    #: the frontend had to guess and guessed ₺ for a dollar-priced stock.
    currency: str = "TRY"
    #: Şirket adı, borsa, ürün türü ve pozisyonun açıldığı tarih. Dördü de
    #: `holdings()` içinde vardı ve bu izdüşümde düşürülüyordu; ana sayfadaki
    #: pozisyon tablosu bu yüzden tür ve tarih sütunlarını dolduramıyordu.
    name: Optional[str] = None
    market: Optional[str] = None
    productType: Optional[str] = None
    openedAt: Optional[datetime] = None


class Order(BaseModel):
    id: str
    symbol: str
    #: Türkçe durum etiketi. Kaynak: `market_service.ORDER_STATUS_TR`.
    #:
    #: Liste bir dönem üç değerdi ve harita ondan GENİŞTİ: `PENDING` ile
    #: `FAILED` haritada hiç yoktu, sessizce "Bekliyor" diye görünüyorlardı.
    #: Haritayı düzeltmek burayı da genişletmeyi gerektirdi -- iki liste
    #: ayrıştığında sonuç 500 oluyor, çünkü şema kendi ürettiğimiz bir
    #: değeri reddediyor.
    status: Literal[
        'Onay bekliyor', 'Fiyat bekliyor', 'İşleniyor',
        'Gerçekleşti', 'İptal edildi', 'Başarısız', 'İptal',
    ]
    type: Literal['Alış', 'Satış']
    quantity: float
    price: float
    total: float
    date: str
    #: The instrument's own currency. Dropped for a long time, which is why
    #: the frontend had to guess and guessed ₺ for a dollar-priced stock.
    currency: str = "TRY"
    #: Kullanıcının verdiği tetikleyici fiyat; piyasa emrinde None.
    limitPrice: Optional[float] = None
    #: Bu emir şu an geri çekilebilir mi. Kaynak:
    #: `market_service.CANCELLABLE_STATUSES`.
    cancellable: bool = False


class CandlestickDataPoint(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    value: Optional[float] = None
    color: Optional[str] = None

class AssetAllocationItem(BaseModel):
    assetClass: str
    percentage: float
    amount: float
    color: str

class WatchlistItem(BaseModel):
    symbol: str
    price: float
    change: float
    changePercent: float
    #: The instrument's own currency. Dropped for a long time, which is why
    #: the frontend had to guess and guessed ₺ for a dollar-priced stock.
    currency: str = "TRY"


class TopMoverItem(BaseModel):
    symbol: str
    price: float
    changePercent: float
    #: The instrument's own currency. Dropped for a long time, which is why
    #: the frontend had to guess and guessed ₺ for a dollar-priced stock.
    currency: str = "TRY"


class SectorAllocationItem(BaseModel):
    sector: str
    percentage: float
    color: str

class HeatmapItem(BaseModel):
    symbol: str
    weight: float
    changePercent: float
    sector: str
    #: The instrument's own currency. Dropped for a long time, which is why
    #: the frontend had to guess and guessed ₺ for a dollar-priced stock.
    currency: str = "TRY"


class OrderProposeRequest(BaseModel):
    """
    AI servisinin işlem önerisi yaparken kullanacağı veri modeli (şeması).
    """
    asset: str
    action: str
    amount: float

class OrderConfirmRequest(BaseModel):
    """
    Frontend tarafının, kullanıcıdan alınan işlem onayını iletirken kullanacağı veri modeli (şeması).
    """
    order_id: str
    action: str


class CashMovementOut(BaseModel):
    """Yatırım hesabının nakit defterinden tek satır.

    `banking.MovementOut` ile kasıtlı olarak aynı alanlar: bankacılık arayüzü
    iki dökümü de aynı satır bileşeniyle basabilsin. Tek fark
    `reference_number`'ın boş olabilmesi -- yöneticinin yaptığı bir düzeltmenin
    banka referansı yoktur ve uydurmak, olmayan bir işleme atıf yapmak olurdu.
    """

    reference_number: Optional[str] = None
    direction: str
    amount: float
    balance_after: float
    counterparty_iban: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime


class CashStatementOut(BaseModel):
    """Yatırım hesabının hareket dökümü."""

    account_number: str
    iban: Optional[str] = None
    balance: float
    currency_code: str
    movements: List[CashMovementOut] = []


class AllocationTargetItem(BaseModel):
    """Bir kova için hedef ağırlık."""

    bucket: str
    label: str = ""
    targetPercent: float = Field(ge=0, le=100)


class AllocationTargetOut(BaseModel):
    #: Hiç hedef girilmemişse boş liste. `hasTarget` ile birlikte okunuyor:
    #: "hedef yok" ile "hedefi sıfırladım" farklı şeyler.
    hasTarget: bool = False
    targets: List[AllocationTargetItem] = Field(default_factory=list)
    updatedAt: Optional[datetime] = None


class AllocationTargetRequest(BaseModel):
    targets: List[AllocationTargetItem] = Field(default_factory=list)


class AllocationDriftBucket(BaseModel):
    bucket: str
    label: str
    amount: float
    #: Portföy boşken None, %0 değil: dağılımı olmayan bir portföye "her
    #: kovada %0" demek, dağılımı varmış gibi göstermek olurdu.
    currentPercent: Optional[float] = None
    #: Hedef koyulmamış kovada None. %0 SAYILMAZ -- "hedefim yok" ile
    #: "hedefim sıfır" farklı şeyler ve ikincisi eldeki her kuruşu sapma
    #: gibi gösterirdi.
    targetPercent: Optional[float] = None
    gapPoints: Optional[float] = None
    #: Hedefe ulaşmak için kaç lira fark var. Pozitif fazla, negatif eksik.
    #: Bir emir DEĞİL: öneri akışını kullanıcı kendisi başlatır.
    gapAmount: Optional[float] = None


class AllocationDriftOut(BaseModel):
    hasTarget: bool = False
    totalValue: float = 0.0
    buckets: List[AllocationDriftBucket] = Field(default_factory=list)
    #: Kodda üretilen cümle. Sapmanın YÖNÜ yanlış okunursa kullanıcı
    #: hedefinin tersine hareket eder; bu, prompt'a ya da arayüze
    #: bırakılacak bir şey değil.
    statement: str = ""
