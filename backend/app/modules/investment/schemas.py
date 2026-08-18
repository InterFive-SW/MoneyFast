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

class Order(BaseModel):
    id: str
    symbol: str
    status: Literal['Bekliyor', 'Gerçekleşti', 'İptal']
    type: Literal['Alış', 'Satış']
    quantity: float
    price: float
    total: float
    date: str

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
    order_id: str = Field(..., description="Onaylanacak siparişin benzersiz ID'si")
    action: str = Field(..., description="İşlem türü: 'buy' veya 'sell'")
    asset: str = Field(..., description="Hisse senedi sembolü (Örn: AAPL)")
    amount: float = Field(..., description="Alınacak/satılacak lot miktarı")
