from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_id
from app.modules.banking import service as banking_service
from app.modules.investment import ai_service, market_service
from . import profile, service
from .schemas import RiskProfileOut, RiskRequest, RiskResponse

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


#: The window the cashflow figures cover. Matches the banking spending
#: endpoint so the two never disagree about what "this month" means.
CASHFLOW_DAYS = 30


@router.get(
    "/profile",
    response_model=RiskProfileOut,
    summary="Kullanıcının risk profili (Risk sayfası)",
)
async def risk_profile(
    lookback: str = "1Y",
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Risk sayfasının okuduğu profil: puan, puanı oluşturan bulgular ve nakit
    akışı.

    `POST /calculate` MCP sözleşmesine dondurulmuş ve ham metrik döner; bu uç
    nokta ekrana göre şekillendirilmiştir ve **kullanıcıya bağlıdır** — pozisyon
    listesini gövdeden almaz, oturumdan çözer.

    Sayfa daha önce tamamen sabit bir fixture'dan besleniyordu: 68 puan, dört
    uydurma bulgu ve hiç ölçülmemiş bir borç/gelir oranı. Buradaki her sayı
    `risk/service.calculate` çıktısına kadar izlenebilir; ham metrikler de
    `metrics` alanında aynen döner.
    """
    holdings = market_service.holdings(db, user_id=user_id)
    quotes = market_service.latest_quotes(db)
    rates = ai_service.fx_rates(quotes)
    warnings: list[str] = []

    positions = []
    for row in holdings:
        if row.get("price") is None:
            warnings.append(f"{row['symbol']}: fiyat yok, hesaba katılmadı")
            continue
        # Converted to one currency before the weights are taken. Comparing a
        # 481-dollar holding against a 404-lira one as though the numbers were
        # commensurate made a 98% position look like half the portfolio, and
        # concentration is computed from exactly these weights.
        value = ai_service.holding_value(row, rates)
        if value is None:
            warnings.append(f"{row['symbol']}: kur bilinmiyor, hesaba katılmadı")
            continue
        positions.append(
            {
                "symbol": row["symbol"],
                "quantity": row["quantity"],
                "market_value": value,
                "asset_class": "EQUITY",
                "sector": row.get("sector") or "UNCLASSIFIED",
                # The key the risk engine actually reads.
                "instrument_currency": row.get("currency") or "TRY",
            }
        )

    metrics: dict = {}
    if positions:
        result = service.calculate(
            positions=positions,
            lookback=lookback,
            closes_for=lambda symbol: market_service.candle_closes(db, symbol),
        )
        metrics = result.get("metrics") or {}
        metrics["data_quality"] = result.get("data_quality") or {}
    else:
        warnings.append("Portföyünüzde değerlenebilir pozisyon bulunamadı.")

    scored = profile.score_from(metrics)
    since = datetime.now(timezone.utc) - timedelta(days=CASHFLOW_DAYS)
    income = banking_service.income_total(db, user_id, since)
    expense = sum(
        row["amount"] for row in banking_service.spending_by_category(db, user_id, since)
    )

    return RiskProfileOut(
        as_of=datetime.now(timezone.utc).isoformat(),
        score=scored["score"],
        level=scored["level"],
        components=scored["components"],
        findings=profile.findings_from(metrics, len(positions)),
        suggestions=profile.suggestions_from(metrics),
        cashflow={
            "period": f"Son {CASHFLOW_DAYS} gün",
            "currency_code": "TRY",
            "monthly_income": income,
            "monthly_expense": round(expense, 2),
            # None rather than 0.0 when nothing came in: a savings rate of
            # zero claims they spent exactly what they earned.
            "savings_rate": (
                round((income - expense) / income, 4) if income else None
            ),
        },
        metrics=metrics,
        position_count=len(positions),
        warnings=warnings,
    )


@router.get("/health", summary="Risk modülü sağlık durumu")
async def health_check():
    return {"status": "ok", "module": "risk"}
