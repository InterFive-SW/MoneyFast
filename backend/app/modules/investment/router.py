from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Dict

from app.core.database import get_db
from app.modules.auth.router import get_current_user
from app.modules.investment import service
from .schemas import (
    InvestmentBalance, Position, Order, CandlestickDataPoint, AssetAllocationItem,
    WatchlistItem, TopMoverItem, DividendItem, SectorAllocationItem, HeatmapItem,
    OrderProposeRequest, OrderConfirmRequest
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

@router.post("/orders/propose", response_model=Dict[str, str])
async def propose_order(request: OrderProposeRequest):
    """
    AI servisi tarafından iletilen işlem önerisini alır ve geçici (mock) bir işlem numarası ile öneri statüsünü döner.
    
    Parametreler:
        request (OrderProposeRequest): Varlık türü, işlem türü ve miktarını içeren veri modeli.
        
    Dönüş:
        Dict[str, str]: İşlem numarası ve 'proposed' statüsünü içeren yanıt.
    """
    return {
        "order_id": "TEST-ORDER-123",
        "status": "proposed"
    }

@router.post("/orders/confirm", response_model=Dict[str, str])
async def confirm_order(
    request: OrderConfirmRequest, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    """
    Frontend tarafında kullanıcı tarafından onaylanan işlemi kesinleştirir ve onay statüsünü döner.
    Veritabanı bağlantısı ile bakiye kontrolü yapar ve işlemi kalıcı hale getirir.
    
    Parametreler:
        request (OrderConfirmRequest): Kullanıcı tarafından onaylanan sipariş detaylarını içeren veri modeli.
        db (Session): SQLAlchemy veritabanı oturumu.
        current_user (dict): Doğrulanmış kullanıcının (şu an için simüle edilmiş) bilgileri.
        
    Dönüş:
        Dict[str, str]: İşlem onay mesajı, statüsü ve yeni bakiye bilgisini içeren yanıt.
    """
    return service.process_order_confirmation(db, current_user, request)


@router.get(
    "/health",
    summary="Investment modülü sağlık durumu"
)
async def health_check():
    """
    Investment modülünün durumunu (health check) kontrol eder.
    Sistemin ayakta olup olmadığını ve doğru modüle ulaşıldığını doğrulamak için kullanılır.
    """
    return {"status": "ok", "module": "investment"}
