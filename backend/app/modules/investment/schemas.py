from datetime import datetime
from pydantic import BaseModel
from typing import List, Literal, Optional

class InvestmentBreakdown(BaseModel):
    cashTRY: float
    stocksBIST: float
    stocksUS: float

class InvestmentBalance(BaseModel):
    totalTRY: float
    totalUSD: float
    breakdown: InvestmentBreakdown

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
    status: Literal['Bekliyor', 'Gerçekleşti', 'İptal']
    type: Literal['Alış', 'Satış']
    quantity: float
    price: float
    total: float
    date: str
    #: The instrument's own currency. Dropped for a long time, which is why
    #: the frontend had to guess and guessed ₺ for a dollar-priced stock.
    currency: str = "TRY"


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
