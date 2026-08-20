from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.investment import market_service
from . import service
from .schemas import RiskRequest, RiskResponse

router = APIRouter(tags=["risk"])


@router.post(
    "/calculate",
    response_model=RiskResponse,
    summary="Portföy risk metrikleri (MCP v2.1 sözleşmesi)",
)
async def calculate_risk(request: RiskRequest, db: Session = Depends(get_db)):
    """
    Verilen pozisyon kümesi için geçmişe dönük (ex-post) risk istatistikleri döner.

    Yoğunlaşma metrikleri (HHI, etkin N, ağırlıklar) tam olarak hesaplanır.
    Volatilite, drawdown, VaR, CVaR, beta ve Sharpe ise `market_candles`'taki
    gerçek günlük kapanışlardan hesaplanır.

    Yeterli geçmişi olmayan enstrümanlar `data_quality.excluded_symbols`'e
    yazılır; komşularından doldurulmaz. Hesaplanamayan bir metrik `None` kalır —
    uydurulmuş bir volatilite değeri, olmayan bir değerden kesinlikle daha
    kötüdür, çünkü olmayan değer olmadığı belli olur.
    """
    if not request.positions:
        # The contract documents this as InvalidInputError rather than an
        # empty result: an empty position set cannot produce a meaningful
        # metric, and a zeroed HHI would render as "perfectly diversified".
        raise HTTPException(status_code=400, detail="positions boş olamaz.")

    return service.calculate(
        positions=[position.model_dump() for position in request.positions],
        # Injected so the service stays free of database concerns and can be
        # tested against hand-built series.
        closes_for=lambda symbol: market_service.candle_closes(db, symbol),
        lookback=request.lookback,
        benchmark_symbol=request.benchmark_symbol,
        metrics=request.metrics,
        confidence_level=request.confidence_level,
        risk_free_rate=request.risk_free_rate,
        rebalance_assumption=request.rebalance_assumption,
    )


@router.get("/health", summary="Risk modülü sağlık durumu")
async def health_check():
    return {"status": "ok", "module": "risk"}
