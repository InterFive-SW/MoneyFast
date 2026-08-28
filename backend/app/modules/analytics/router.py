"""Portföy Analizi uç noktaları.

`investment` ve `risk` modüllerindeki hesapları tekrar etmez, onları
birleştirir: dağılım `market_service.holdings`'ten, trend `market_candles`'tan,
gerçekleşen işlemler `transaction_proposals`'tan gelir. Aynı kaynaklar olduğu
için analiz ekranı ile gösterge paneli portföyün değeri konusunda birbiriyle
çelişemez.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_optional_user_id
from app.modules.investment import ai_service, market_service
from app.modules.investment.models import TransactionProposal

from . import service
from .deps import lookback_param
from .schemas import PortfolioAnalysis

router = APIRouter(tags=["analytics"])


@router.get(
    "/portfolio",
    response_model=PortfolioAnalysis,
    summary="Portföy analizi (dağılım, trend, performans, işlem geçmişi)",
)
async def portfolio_analysis(
    lookback: str = Depends(lookback_param),
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """
    Portföy Analizi ekranının tek çağrısı.

    Tek uç nokta olmasının sebebi User Story'deki 2 saniyelik yükleme bütçesi:
    dağılım, trend ve performans için ayrı ayrı istek atmak, aynı pozisyon
    listesini üç kez okumak demekti.

    Kimliği doğrulanmamış çağıran demo hesabını görür; oturum açmış kullanıcı
    yalnızca kendi verisini görür (İK-19).
    """
    holdings = market_service.holdings(db, user_id=user_id)
    quotes = market_service.latest_quotes(db)
    as_of, delay_minutes, _ = market_service.freshness(quotes)
    account = market_service.account(db, user_id=user_id)

    proposals = (
        db.query(TransactionProposal)
        .filter(TransactionProposal.user_id == user_id)
        .all()
        if user_id
        else []
    )

    return service.build(
        db,
        user_id=user_id,
        holdings=holdings,
        cash=float(account.cash_balance) if account else 0.0,
        sector_map=market_service.sector_by_symbol(db),
        # Injected so the service stays pure and testable without a session,
        # matching how risk/service.py takes its price reader.
        # The window the caller asked for, resolved the same way `risk` does
        # it. One selector drives both endpoints; a fixed window here would
        # leave the trend chart still showing a year while the metrics
        # beside it moved to three months.
        closes_for=lambda symbol: market_service.candle_closes(
            db, symbol, limit=service.window_limit(lookback)
        ),
        proposals=proposals,
        as_of=as_of,
        delay_minutes=delay_minutes,
        # Same helper the portfolio summary uses, so the two pages cannot
        # disagree about what a dollar is worth.
        rates=ai_service.fx_rates(quotes),
        base_currency=(account.currency_code if account else "TRY") or "TRY",
    )


@router.get("/health", summary="Analytics modülü sağlık durumu")
async def health_check():
    """
    Analytics modülünün durumunu (health check) kontrol eder.
    Sistemin ayakta olup olmadığını ve doğru modüle ulaşıldığını doğrulamak için kullanılır.
    """
    return {"status": "ok", "module": "analytics"}
