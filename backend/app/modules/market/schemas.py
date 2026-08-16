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
