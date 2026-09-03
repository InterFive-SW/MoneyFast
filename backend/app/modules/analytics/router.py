"""Portföy Analizi uç noktaları.

`investment` ve `risk` modüllerindeki hesapları tekrar etmez, onları
birleştirir: dağılım `market_service.holdings`'ten, trend `market_candles`'tan,
gerçekleşen işlemler `transaction_proposals`'tan gelir. Aynı kaynaklar olduğu
için analiz ekranı ile gösterge paneli portföyün değeri konusunda birbiriyle
çelişemez.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core import pdf_generator
from app.core.database import get_db
from app.core.deps import get_optional_user_id, require_service_token
from app.modules.investment import ai_service, market_service
from app.modules.investment.models import TransactionProposal

from . import report, service
from .deps import lookback_param
from .schemas import PortfolioAnalysis, PortfolioReport

log = logging.getLogger("moneyfast.analytics")

router = APIRouter(tags=["analytics"])


@router.get(
    "/portfolio",
    response_model=PortfolioAnalysis,
    summary="Portföy analizi (dağılım, trend, performans, işlem geçmişi)",
)
def portfolio_analysis(
    # İki ayrı boyut: `lookback` ÖLÇÜM PENCERESİ (risk ile ortak seçici),
    # `range` ise ÇÖZÜNÜRLÜK (gün içi mi, günlük mü). Tek parametreye
    # sıkıştırmak "son bir yıl" ile "bugünü dakika dakika" arasındaki farkı
    # kaybetmek olurdu.
    lookback: str = Depends(lookback_param),
    range: str = Query(default="all", pattern="^(all|day)$"),
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
    as_of, delay_minutes, _, _stale = market_service.freshness(quotes)
    account = market_service.account(db, user_id=user_id)

    proposals = (
        db.query(TransactionProposal)
        .filter(TransactionProposal.user_id == user_id)
        .all()
        if user_id
        else []
    )

    intraday = range == "day"

    return service.build(
        db,
        user_id=user_id,
        holdings=holdings,
        cash=float(account.cash_balance) if account else 0.0,
        sector_map=market_service.sector_by_symbol(db),
        # Injected so the service stays pure and testable without a session,
        # matching how risk/service.py takes its price reader.
        # Pencere çağıranın istediği, `risk` ile aynı şekilde çözülüyor: tek
        # seçici iki uç noktayı birden sürüyor. Sabit bir pencere, ölçümler üç
        # aya geçerken grafiğin bir yıl göstermeye devam etmesi demekti.
        #
        # Gün içi görünüm 5 dakikalık gerçek barlardan okunuyor; o durumda
        # pencere bar sayısıyla değil, aralıkla belirleniyor.
        closes_for=lambda symbol: market_service.candle_closes(
            db,
            symbol,
            limit=service.INTRADAY_WINDOW if intraday else service.window_limit(lookback),
            interval="5m" if intraday else "1d",
        ),
        proposals=proposals,
        as_of=as_of,
        delay_minutes=delay_minutes,
        # Same helper the portfolio summary uses, so the two pages cannot
        # disagree about what a dollar is worth.
        rates=ai_service.fx_rates(quotes),
        base_currency=(account.currency_code if account else "TRY") or "TRY",
        intraday=intraday,
        # Geçmiş kur, o günün kendi mumundan: USDTRY'nin serisi zaten
        # elimizde. Bütün geçmişi bugünün kuruyla çevirmek, portföyün
        # geçmişini bugünün kurunun hikâyesiyle karıştırırdı.
        fx_closes_for=lambda code: market_service.candle_closes(
            db,
            f"{code}{(account.currency_code if account else 'TRY') or 'TRY'}",
            limit=service.INTRADAY_WINDOW if intraday else service.TREND_WINDOW,
            interval="5m" if intraday else "1d",
        ),
    )


@router.get("/health", summary="Analytics modülü sağlık durumu")
async def health_check():
    """
    Analytics modülünün durumunu (health check) kontrol eder.
    Sistemin ayakta olup olmadığını ve doğru modüle ulaşıldığını doğrulamak için kullanılır.
    """
    return {"status": "ok", "module": "analytics"}


@router.get(
    "/report",
    response_model=PortfolioReport,
    summary="Detaylı rapor (tek çağrı)",
)
def portfolio_report(
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """
    "Detaylı Rapor Oluştur" düğmesinin tek çağrısı.

    Proje dokümanı bu düğmeyi adıyla istiyor: tek tıkla kapsamlı analiz
    raporu. Yeni bir ölçüm yapmıyor -- her bölüm zaten var olan bir servisten
    okuyor ve cümleler `report.py`'de bir kez kuruluyor, ekran ile PDF ile
    sohbet aynı metni okusun diye.
    """
    return report.build_report(db, user_id)


@router.get(
    "/report.pdf",
    summary="Detaylı rapor (PDF)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def portfolio_report_pdf(
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """
    Aynı rapor, indirilebilir belge olarak.

    METİN ÜRETMİYOR: bölümler `report.build_report`'tan geliyor ve PDF
    yalnızca onları sayfaya yerleştiriyor. Ekran, sohbet ve PDF aynı metni
    okumalı.

    Font kurulu değilse 503: aksanları düşürülmüş Türkçe yanlış yazılmış
    Türkçedir ve kullanıcıya gösterilen bir belgede sessizce bozuk metin, hiç
    belge olmamasından kötüdür. Kurulum eksikliği de kullanıcının
    düzeltebileceği bir şey değil, o yüzden 4xx değil.
    """
    data = report.build_report(db, user_id)
    try:
        content = pdf_generator.generate_report_pdf(data)
    except pdf_generator.UnicodeFontMissing as exc:
        log.error("report pdf unavailable, unicode font missing: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="PDF üretimi için gerekli yazı tipi kurulu değil.",
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="moneyfast-rapor-{stamp}.pdf"'
        },
    )


@router.get(
    "/report/{user_id}",
    response_model=PortfolioReport,
    dependencies=[Depends(require_service_token)],
    summary="Detaylı rapor (MCP sözleşmesi)",
)
def portfolio_report_for_ai(user_id: str, db: Session = Depends(get_db)):
    """
    Yukarıdakiyle aynı rapor, kullanıcısı yoldan gelen hâli.

    Konusunu YOLDA adlandırıyor, dolayısıyla servis token'ı istiyor: rapor
    pozisyonları, bakiyeyi, maaşı ve kira giderini bir arada taşıyor ve bu,
    ayrı ayrı korunan uçların hepsinin toplamı.
    """
    return report.build_report(db, user_id)
