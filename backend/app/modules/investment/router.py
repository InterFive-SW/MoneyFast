from fastapi import APIRouter
from typing import List, Dict

from .schemas import (
    InvestmentBalance, Position, Order, CandlestickDataPoint, AssetAllocationItem,
    WatchlistItem, TopMoverItem, DividendItem, SectorAllocationItem, HeatmapItem
)
from .mock_data import (
    MOCK_INVESTMENT_BALANCE, MOCK_POSITIONS, MOCK_ORDERS, MOCK_CHART_DATA, MOCK_ASSET_ALLOCATION,
    MOCK_WATCHLIST, MOCK_TOP_MOVERS, MOCK_DIVIDENDS, MOCK_SECTOR_ALLOCATION, MOCK_HEATMAP
)

router = APIRouter(tags=["investment"])

@router.get("/portfolio/summary", response_model=InvestmentBalance)
async def get_portfolio_summary():
    """
    Kullanıcının yatırım hesabının toplam bakiyesini ve kırılımlarını (Nakit, BIST, ABD vb.) döner.
    """
    return MOCK_INVESTMENT_BALANCE

@router.get("/portfolio/chart", response_model=Dict[str, List[CandlestickDataPoint]])
async def get_portfolio_chart():
    """
    Portföy performans grafiği için farklı zaman dilimlerine göre (Gün, Hafta, Ay vb.)
    mum (candlestick) ve hacim (volume) verilerini döner.
    """
    return MOCK_CHART_DATA

@router.get("/positions", response_model=List[Position])
async def get_positions():
    """
    Kullanıcının sahip olduğu açık yatırım pozisyonlarını döner.
    """
    return MOCK_POSITIONS

@router.get("/orders", response_model=List[Order])
async def get_orders():
    """
    Kullanıcının geçmiş ve bekleyen alım/satım emirlerini döner.
    """
    return MOCK_ORDERS

@router.get("/asset-allocation", response_model=List[AssetAllocationItem])
async def get_asset_allocation():
    """
    Portföyün varlık sınıflarına (Hisse, Altın, Döviz vb.) göre dağılımını döner.
    """
    return MOCK_ASSET_ALLOCATION

@router.get("/watchlist", response_model=Dict[str, List[WatchlistItem]])
async def get_watchlist():
    """
    İzleme listesindeki varlıkları döner.
    """
    return MOCK_WATCHLIST

@router.get("/top-movers", response_model=Dict[str, List[TopMoverItem]])
async def get_top_movers():
    """
    Günün en çok kazandıran ve kaybettiren hisselerini döner.
    """
    return MOCK_TOP_MOVERS

@router.get("/dividends", response_model=List[DividendItem])
async def get_dividends():
    """
    Yaklaşan temettü tarihlerini ve detaylarını döner.
    """
    return MOCK_DIVIDENDS

@router.get("/sector-allocation", response_model=List[SectorAllocationItem])
async def get_sector_allocation():
    """
    Hisse senedi portföyünün sektörel dağılımını döner.
    """
    return MOCK_SECTOR_ALLOCATION

@router.get("/heatmap", response_model=List[HeatmapItem])
async def get_heatmap():
    """
    Isı haritası (heatmap) için gerekli olan verileri döner.
    """
    return MOCK_HEATMAP
