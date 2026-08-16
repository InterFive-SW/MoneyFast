from fastapi import APIRouter
from typing import List

from .schemas import MarketTicker, NewsItem
from .mock_data import MOCK_MARKET_TICKERS, MOCK_NEWS

router = APIRouter(tags=["market"])

@router.get("/tickers", response_model=List[MarketTicker])
async def get_market_tickers():
    """
    Kullanıcının gösterge panelindeki (dashboard) mini ticker bileşenleri
    için Borsa, Kripto ve Döviz anlık fiyatlarını döner.
    Şu an mock veri dönmektedir, ileride yfinance entegrasyonu yapılacaktır.
    """
    return MOCK_MARKET_TICKERS

@router.get("/news", response_model=List[NewsItem])
async def get_market_news():
    """
    Piyasa haber akışını döner.
    Şu an mock veri dönmektedir, ileride RSS/Scraping entegrasyonu yapılacaktır.
    """
    return MOCK_NEWS
