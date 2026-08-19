from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CurrencyCode = Literal["TRY", "USD"]


class InvestmentBreakdown(BaseModel):
    cashTRY: float
    stocksBIST: float
    cashUSD: float
    stocksUSUSD: float


class InvestmentBalance(BaseModel):
    totalTRY: float = Field(
        description="TRY cinsinden nakit ve varlıkların toplamı; kur dönüşümü içermez."
    )
    totalUSD: float = Field(
        description="USD cinsinden nakit ve varlıkların toplamı; kur dönüşümü içermez."
    )
    breakdown: InvestmentBreakdown


class Position(BaseModel):
    symbol: str
    currencyCode: CurrencyCode
    # Price-dependent fields are null when neither a market quote nor the
    # position's cached current price is available. Returning zero would
    # fabricate a financial value.
    price: float | None
    quantity: float
    avgCost: float
    totalValue: float | None
    dailyReturn: float | None
    dailyReturnPercent: float | None
    totalReturn: float | None
    totalReturnPercent: float | None
    priceAsOf: datetime | None
    priceSource: str | None


class Order(BaseModel):
    id: str
    symbol: str
    status: Literal["Bekliyor", "Kısmi", "Gerçekleşti", "İptal"]
    type: Literal["Alış", "Satış"]
    currencyCode: CurrencyCode
    quantity: float
    executedQuantity: float | None
    price: float | None
    total: float | None
    date: datetime | None


class InvestmentTransaction(BaseModel):
    id: str
    orderId: str
    symbol: str
    type: Literal["Alış", "Satış"]
    currencyCode: CurrencyCode
    quantity: float
    price: float
    grossAmount: float
    commission: float
    tax: float
    total: float
    executedAt: datetime


class CandlestickDataPoint(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    value: float | None = None
    color: str | None = None


class AssetAllocationItem(BaseModel):
    assetClass: str
    percentage: float
    amount: float
    currencyCode: CurrencyCode
    color: str


class WatchlistItem(BaseModel):
    symbol: str
    price: float
    change: float
    changePercent: float


class TopMoverItem(BaseModel):
    symbol: str
    price: float
    changePercent: float


class DividendItem(BaseModel):
    symbol: str
    exDate: str
    paymentDate: str
    amount: float
    yieldPercent: float


class SectorAllocationItem(BaseModel):
    sector: str
    percentage: float
    color: str


class HeatmapItem(BaseModel):
    symbol: str
    weight: float
    changePercent: float
    sector: str


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
