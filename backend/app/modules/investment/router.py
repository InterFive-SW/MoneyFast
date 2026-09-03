from datetime import datetime, timezone
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Header, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Optional

from app.core.database import get_db, SessionLocal
from app.core.deps import get_current_user_id, get_optional_user_id
from app.modules.auth.models import User
from app.core.email import send_transaction_email, send_transaction_request_email
from app.modules.notification.models import Notification
from . import ai_service, allocation, market_service, service
from app.modules.analytics import service as analytics_service
from app.core.deps import require_service_token
from .models import AllocationTarget, TransactionProposal
from .ai_schemas import (
    PortfolioPositionsOut, StageTransactionRequest, StageTransactionOut,
)
from .schemas import (
    AllocationDriftOut,
    AllocationTargetOut,
    AllocationTargetRequest,
    InvestmentBalance, Position, Order, CandlestickDataPoint, AssetAllocationItem,
    WatchlistItem, TopMoverItem, SectorAllocationItem, HeatmapItem,
    OrderProposeRequest, OrderConfirmRequest, CashStatementOut
)

router = APIRouter(tags=["investment"])

@router.get("/portfolio/summary", response_model=InvestmentBalance)
def get_portfolio_summary(
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """
    Yatırım hesabının toplam bakiyesi ve kırılımı (nakit, BIST, ABD).

    Canlı fiyatlardan hesaplanır; saklanan bir toplam yok. Saklansaydı, fiyat
    her değiştiğinde pozisyonların toplamıyla uyuşmazdı.
    """
    rows = market_service.holdings(db, user_id=user_id)
    quotes = market_service.latest_quotes(db)
    rates = ai_service.fx_rates(quotes)
    account = market_service.account(db, user_id=user_id)
    cash = float(account.cash_balance) if account else 0.0

    # Split by the holding's own currency, not by whether its market is BIST.
    # The old test was right only while every foreign holding happened to be
    # American; a EUR instrument was converted at the dollar rate.
    bist = sum(
        value for value in (
            ai_service.holding_value(r, rates) for r in rows
            if (r.get("currency") or "TRY") == "TRY"
        ) if value is not None
    )
    foreign_try = sum(
        value for value in (
            ai_service.holding_value(r, rates) for r in rows
            if (r.get("currency") or "TRY") != "TRY"
        ) if value is not None
    )
    usd_rate = rates.get("USD")

    total_try = cash + bist + foreign_try
    return {
        "totalTRY": round(total_try, 2),
        # Reported as 0 rather than an invented figure when the rate is not in
        # yet; the TRY total is still correct on its own terms.
        "totalUSD": round(total_try / usd_rate, 2) if usd_rate else 0.0,
        "breakdown": {
            "cashTRY": round(cash, 2),
            "stocksBIST": round(bist, 2),
            "stocksUS": round(foreign_try, 2),
        },
    }

@router.get("/portfolio/chart", response_model=Dict[str, List[CandlestickDataPoint]])
def get_portfolio_chart(
    range: str = Query(default="yil"),
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """Portföyün KENDİ değerinin mum serisi.

    Bu uç nokta uzun süre `XU100` döndürüyordu -- BIST 100 endeksini, "Portföy
    Performansı" başlığının altında. Gerekçesi de buradaydı: "portföyün kendi
    zaman serisi ancak günlük anlık görüntüler biriktikçe oluşur". O gerekçe
    artık geçerli değil: seri, elde olan mumlardan ve pozisyonların zaman
    içindeki miktarından hesaplanabiliyor.

    **Tek pencere hesaplanır.** Önceden beş pencerenin hepsi her istekte
    üretiliyordu ve her biri bütün pozisyonların barlarını yeniden okuyordu:
    çağrı başına ~130 sorgu, ölçülen 5,9 saniye ve 173 KB yanıt. Arayüz aynı
    anda tek bir aralık gösteriyor, dolayısıyla tek bir aralık dönüyor.

    Bilinmeyen bir aralık adı sessizce varsayılana düşmez: ekranda hangi
    aralığın çizildiğini bilmemek, yanlış aralığı doğru sanmaktan kötüdür.
    """
    if range not in analytics_service.CANDLE_RANGES:
        raise HTTPException(
            status_code=422,
            detail=f"Bilinmeyen aralık: {range}. "
                   f"Geçerli olanlar: {', '.join(analytics_service.CANDLE_RANGES)}.",
        )

    holdings = market_service.holdings(db, user_id=user_id)
    priced = [row for row in holdings if row.get("price") is not None]
    proposals = _confirmed_proposals(db, user_id)

    account = market_service.account(db, user_id=user_id)
    base_currency = (getattr(account, "currency_code", None) or "TRY")
    quotes = market_service.latest_quotes(db)

    interval, bucket, window, limit = analytics_service.CANDLE_RANGES[range]

    # Tek pencere hesaplandığı için her sembol tam bir kez okunuyor; ara
    # bellek gerekmiyor. Beş pencerenin hepsi üretilirken aynı barlar beş kez
    # çekiliyordu -- çözüm önbellek değil, istenmeyen dört pencereyi hiç
    # hesaplamamaktı.
    def bars_for(symbol: str) -> list:
        return market_service.candle_bars(db, symbol, limit=limit, interval=interval)

    def fx_for(code: str) -> list:
        return market_service.candle_closes(
            db, f"{code}{base_currency}", limit=limit, interval=interval
        )

    # Para birimleri toplanmadan ÖNCE çevrilir, geçmiş kurla.
    rate_at = analytics_service._rate_lookup(
        priced, base_currency, fx_for, ai_service.fx_rates(quotes),
    )
    candles = analytics_service.portfolio_candles(
        priced,
        bars_for=bars_for,
        proposals=proposals,
        bucket_seconds=bucket,
        rate_at=rate_at,
        window_days=window,
    )
    return {
        range: [
            {
                **candle,
                # Portföyün hacmi yoktur; alan sözleşmede olduğu için sıfır
                # geçiliyor, arayüz hacim panelini çizmiyor.
                "value": 0,
                "color": "#22c55e" if candle["close"] >= candle["open"] else "#ef4444",
            }
            for candle in candles
        ]
    }


def _confirmed_proposals(db: Session, user_id: Optional[str]) -> list:
    """Onaylanmış işlemler -- pozisyonun zaman içindeki miktarını veren tek kayıt."""
    if not user_id:
        return []
    return (
        db.query(TransactionProposal)
        .filter(
            TransactionProposal.user_id == user_id,
            TransactionProposal.status == "CONFIRMED",
        )
        .all()
    )


@router.get("/positions", response_model=List[Position])
def get_positions(
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """
    Açık yatırım pozisyonları.

    Miktar ve ortalama maliyet veritabanında; fiyat ve türetilen her değer
    canlı. Sohbet botunun okuduğu `market_service.holdings()` fonksiyonunun
    aynısı, dolayısıyla iki yüzeyin farklı rakam göstermesi mümkün değil.
    """
    return [_as_frontend_position(row) for row in market_service.holdings(db, user_id=user_id)]


def _as_frontend_position(row: dict) -> dict:
    """Project a holding onto the camelCase shape the dashboard expects.

    Every figure is recomputed from the live price. An unpriced instrument
    reports zeros with a zero price, which reads as "no quote" rather than as
    a holding that lost its value.
    """
    price = row.get("price") or 0.0
    quantity = row["quantity"]
    avg_cost = row["avg_cost"]
    previous = row.get("previous_close")
    daily = (price - previous) * quantity if (previous and price) else 0.0
    return {
        "symbol": row["symbol"],
        # `holdings()` bunları zaten taşıyordu; burada düşürülüyorlardı.
        # `currency` ile aynı hikâye: ana sayfadaki "Son Pozisyonlar" tablosu
        # tür ve giriş tarihi sütunlarını dolduramadığı için o sütunlar boş
        # kalıyordu -- veri eksik olduğu için değil, sorulmadığı için.
        "name": row.get("name"),
        "market": row.get("market"),
        "productType": row.get("product_type"),
        "openedAt": row.get("opened_at"),
        # Carried through. `holdings()` had it all along; dropping it here is
        # why the dashboard rendered a dollar price under a "Pozisyon (₺)"
        # heading.
        "currency": row.get("currency") or "TRY",
        "price": round(price, 4),
        "quantity": quantity,
        "avgCost": round(avg_cost, 4),
        "totalValue": round(price * quantity, 2),
        "dailyReturn": round(daily, 2),
        "dailyReturnPercent": round(row.get("change_percent") or 0.0, 2),
        "totalReturn": round((price - avg_cost) * quantity, 2),
        "totalReturnPercent": round((price - avg_cost) / avg_cost * 100, 2) if avg_cost else 0.0,
    }


@router.get("/orders", response_model=List[Order])
def get_orders(db: Session = Depends(get_db)):
    """
    Geçmiş ve bekleyen emirler.

    Kaynak `investment.transaction_proposals`: sohbette gerçekten hazırlanmış
    ve onaylanmış öneriler. Uydurma emir listesi göstermiyoruz — kullanıcının
    vermediği bir emri geçmişinde görmesi, gerçekten verilmiş sanmasına yol
    açar.
    """
    return market_service.recent_orders(db)



@router.get(
    "/accounts/{identifier}/statement",
    response_model=CashStatementOut,
    summary="Yatırım hesabı hareketleri",
)
def cash_statement(
    identifier: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Yatırım hesabının nakit hareketleri.

    Hesap IBAN'ıyla ya da hesap numarasıyla çağrılabilir; bankacılık arayüzü
    elindeki iki alandan hangisi doluysa onu gönderiyor.

    Bankacılık dökümüyle aynı 404 kuralı: başkasının hesabının var olduğunu
    doğrulamak bile fazla bilgi.
    """
    account = market_service.account(db, user_id=user_id, allow_demo_fallback=False)
    if account is None:
        raise HTTPException(status_code=404, detail="Hesap bulunamadı.")

    wanted = identifier.replace(" ", "").upper()
    known = {
        (account.account_number or "").replace(" ", "").upper(),
        (account.iban or service.iban_for(account.account_number)).replace(" ", "").upper(),
    }
    if wanted not in known:
        raise HTTPException(status_code=404, detail="Hesap bulunamadı.")

    return service.cash_statement(db, account, limit=limit)

@router.get("/asset-allocation", response_model=List[AssetAllocationItem])
def get_asset_allocation(
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """Varlık sınıflarına göre dağılım: nakit, BIST hisseleri, yabancı hisseler."""
    rows = market_service.holdings(db, user_id=user_id)
    quotes = market_service.latest_quotes(db)
    rates = ai_service.fx_rates(quotes)
    account = market_service.account(db, user_id=user_id)

    # Kovalar `allocation.py`'de, tek kaynak. Burada ikinci bir liste tutmak,
    # hedef karşılaştırmasının farklı adlarla okuması demekti -- bu depoda
    # aynı hata `sort_by` ve `market` filtresi için iki kez ölçüldü.
    valued = []
    for row in rows:
        value = ai_service.holding_value(row, rates)
        if value is not None:
            valued.append((row, value))
    amounts = allocation.current_amounts(
        valued, float(account.cash_balance) if account else 0.0
    )
    grand = sum(amounts.values())
    # An empty bucket is noise on a pie chart; cash is kept even at zero
    # because "no cash" is itself worth seeing.
    buckets = {
        allocation.label_for(key): amount
        for key, amount in amounts.items()
        if amount or key == allocation.CASH
    }
    palette = {
        allocation.label_for(key): allocation.colour_for(key)
        for key in allocation.BUCKETS
    }
    return [
        {
            "assetClass": name,
            "percentage": round(amount / grand * 100, 2) if grand else 0.0,
            "amount": round(amount, 2),
            "color": palette[name],
        }
        for name, amount in buckets.items()
    ]


@router.get("/watchlist", response_model=Dict[str, List[WatchlistItem]])
def get_watchlist(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Kullanıcının kendi izleme listesi — canlı fiyatlarla, piyasaya göre
    gruplanmış.

    Önceden bu uç nokta alfabetik olarak ilk sekiz hisseyi döndürüyordu:
    herkese aynı liste, kimsenin seçimini yansıtmayan ve arayüzden
    değiştirilemeyen bir "izleme listesi". Artık `watchlist_items`'tan
    okunuyor ve boşsa BOŞ döner — kullanıcının seçmediği bir hisseyi onun
    listesiymiş gibi göstermek, listenin anlamını ortadan kaldırır.

    Gruplar: `bist`, `global` ve hepsini içeren `all`. Değişim yüzdesi
    bilinmeyen enstrümanlar da listelenir; kullanıcı onu bilerek ekledi ve
    listeden sessizce düşmesi, eklemenin işe yaramadığı izlenimi verir.
    """
    symbols = market_service.watchlist_symbols(db, user_id)
    if not symbols:
        return {"bist": [], "global": [], "all": []}

    products = {p.symbol: p for p in market_service.list_products(db, only_priced=False)}
    quotes = market_service.latest_quotes(db, symbols)

    groups: Dict[str, List[dict]] = {"bist": [], "global": [], "all": []}
    # Kullanıcının ekleme sırası korunur; alfabetik sıralamak, kişinin
    # listesini kendi kurduğu düzenden çıkarır.
    for symbol in symbols:
        product = products.get(symbol)
        quote = quotes.get(symbol)
        if product is None or quote is None:
            continue
        row = {
            "symbol": symbol,
            "currency": quote.get("currency") or "TRY",
            "price": round(quote["price"], 4),
            "change": round(quote.get("change_amount") or 0.0, 4),
            "changePercent": round(quote.get("change_percent") or 0.0, 2),
        }
        groups["bist" if product.market == "BIST" else "global"].append(row)
        groups["all"].append(row)
    return groups


@router.post("/watchlist/{symbol}", response_model=Dict[str, str])
def add_to_watchlist(
    symbol: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """İzleme listesine ekler. Aynı hisseyi iki kez eklemek hata değildir."""
    product = market_service.watchlist_add(db, user_id, symbol)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Bilinmeyen sembol: {symbol}")
    return {"symbol": product.symbol, "status": "added"}


@router.delete("/watchlist/{symbol}", response_model=Dict[str, str])
def remove_from_watchlist(
    symbol: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """İzleme listesinden çıkarır."""
    if not market_service.watchlist_remove(db, user_id, symbol):
        raise HTTPException(status_code=404, detail=f"İzleme listesinde yok: {symbol}")
    return {"symbol": symbol.upper(), "status": "removed"}


@router.get("/top-movers", response_model=Dict[str, List[TopMoverItem]])
def get_top_movers(db: Session = Depends(get_db), limit: int = Query(default=5, ge=1, le=20)):
    """
    Günün en çok kazandıran ve kaybettiren hisseleri — "yükselenler/düşenler".

    Yalnızca hisse ürünleri değerlendirilir; endeks ve döviz satırları bir
    "hisse" listesinde yer almamalı. Değişim yüzdesi bilinmeyen enstrümanlar
    listelenmez.
    """
    products = {p.symbol: p for p in market_service.list_products(db, only_priced=False)}
    quotes = market_service.latest_quotes(db)

    rows = [
        {
            "symbol": symbol,
            "currency": quote.get("currency") or "TRY",
            "price": quote["price"],
            "changePercent": round(float(quote["change_percent"]), 2),
        }
        for symbol, quote in quotes.items()
        if quote.get("change_percent") is not None
        and getattr(products.get(symbol), "product_type", None) == "stock"
    ]
    ranked = sorted(rows, key=lambda row: row["changePercent"], reverse=True)
    return {
        "gainers": [row for row in ranked if row["changePercent"] > 0][:limit],
        "losers": [row for row in reversed(ranked) if row["changePercent"] < 0][:limit],
    }


@router.get("/sector-allocation", response_model=List[SectorAllocationItem])
def get_sector_allocation(
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """
    Portföyün sektörel dağılımı — `instrument_fundamentals` satırlarından.

    Sektörü bilinmeyen pozisyonlar "Bilinmiyor" altında toplanır; tahmin
    yürüterek sektör atamak, dağılımı olduğundan daha kesin gösterirdi.
    """
    rows = market_service.holdings(db, user_id=user_id)
    sectors = market_service.sector_by_symbol(db)
    rates = ai_service.fx_rates(market_service.latest_quotes(db))

    totals: Dict[str, float] = {}
    for row in rows:
        # Converted before summing. Adding a USD position straight into a TRY
        # total made every percentage on this chart wrong whenever the user
        # held a foreign name.
        value = ai_service.holding_value(row, rates)
        if value is None:
            continue
        sector = sectors.get(row["symbol"]) or "Bilinmiyor"
        totals[sector] = totals.get(sector, 0.0) + value

    grand = sum(totals.values())
    palette = ["#0ea5e9", "#22c55e", "#f59e0b", "#a855f7", "#ef4444", "#14b8a6", "#64748b"]
    return [
        {
            "sector": sector,
            "percentage": round(value / grand * 100, 2) if grand else 0.0,
            "color": palette[index % len(palette)],
        }
        for index, (sector, value) in enumerate(
            sorted(totals.items(), key=lambda item: item[1], reverse=True)
        )
    ]


@router.get("/heatmap", response_model=List[HeatmapItem])
def get_heatmap(
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """Isı haritası: portföy ağırlığı ve günlük değişim."""
    sectors = market_service.sector_by_symbol(db)
    rates = ai_service.fx_rates(market_service.latest_quotes(db))

    # Weights are shares of one total, so every value must be in one currency.
    valued = []
    for row in market_service.holdings(db, user_id=user_id):
        value = ai_service.holding_value(row, rates)
        if value is not None:
            valued.append((row, value))

    grand = sum(value for _, value in valued)
    return [
        {
            "symbol": row["symbol"],
            "currency": row.get("currency") or "TRY",
            "weight": round(value / grand * 100, 2) if grand else 0.0,
            "changePercent": round(row.get("change_percent") or 0.0, 2),
            "sector": sectors.get(row["symbol"]) or "Bilinmiyor",
        }
        for row, value in valued
    ]


# ---------------------------------------------------------------------------
# AI-facing endpoints
#
# Consumed by the MCP tool server, not by the frontend. Their payload shapes
# are frozen against "MCP Tools Interface Definitions v2.1": the tool layer
# raises ContractViolationError on a missing key rather than defaulting it, so
# these responses must be complete rather than convenient. The frontend
# endpoints above are unaffected and keep their camelCase rendering shapes.
# ---------------------------------------------------------------------------


@router.get(
    "/portfolio/{user_id}/positions",
    response_model=PortfolioPositionsOut,
    summary="Portföy pozisyonları (MCP v2.1 sözleşmesi)",
    dependencies=[Depends(require_service_token)],
)
def get_portfolio_positions_for_ai(
    user_id: str,
    db: Session = Depends(get_db),
    account_ids: Optional[List[str]] = Query(default=None),
    asset_classes: Optional[List[str]] = Query(default=None),
    include_closed: bool = Query(default=False),
    base_currency: str = Query(default="TRY"),
    valuation_mode: str = Query(default="LAST_CLOSE"),
):
    """
    Kullanıcının pozisyonlarını, AI ajanlarının beklediği sözleşme biçiminde döner.

    Frontend'in kullandığı `/positions` ile aynı veri kaynağını
    kullanır; iki uç noktanın kullanıcının neye sahip olduğu konusunda
    çelişmesi bu sayede mümkün değildir.
    """
    currency = base_currency.upper()
    if currency not in ai_service.SUPPORTED_BASE_CURRENCIES:
        # Deterministic client error: the MCP layer maps 400 to
        # InvalidInputError, which tells the agent to correct and retry rather
        # than to treat the portfolio as unavailable.
        raise HTTPException(
            status_code=400,
            detail=(
                f"Desteklenmeyen base_currency: {base_currency}. "
                f"Desteklenenler: {', '.join(sorted(ai_service.SUPPORTED_BASE_CURRENCIES))}"
            ),
        )

    # One source of prices for the chatbot and the dashboard. Reading them
    # here rather than inside ai_service keeps that module free of database
    # concerns and unit-testable without a session.
    quotes = market_service.latest_quotes(db)
    owner = market_service.account(db, user_id=user_id)
    payload, _ = ai_service.build_portfolio(
        user_id=user_id,
        holdings=market_service.holdings(db, user_id=user_id),
        # Cash, so the assistant can answer "bakiyem ne kadar" instead of
        # quoting the portfolio's market value as if it were a balance.
        cash_balance=float(owner.cash_balance) if owner is not None else None,
        account_ids=account_ids,
        asset_classes=asset_classes,
        include_closed=include_closed,
        base_currency=currency,
        valuation_mode=valuation_mode,
        quotes=quotes,
        freshness=market_service.freshness(quotes),
    )
    return payload


@router.post(
    "/transactions/stage",
    response_model=StageTransactionOut,
    summary="İşlem önerisi hazırla (MCP v2.1 sözleşmesi)",
)
def stage_transaction(
    request: StageTransactionRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    authenticated_user_id: Optional[str] = Depends(get_optional_user_id),
):
    """
    Bir işlemi doğrular, maliyetlendirir ve **yalnızca öneri olarak** bekletir.

    Bu uç nokta hiçbir emir iletmez. `confirmation_required` her zaman True
    döner ve onay, frontend'deki ayrı onay yüzeyinde kullanıcı tarafından
    verilir; `/orders/confirm` o ayrı yoldur.

    `Idempotency-Key` başlığı ile gövdedeki `idempotency_key` çelişirse istek
    reddedilir: bir proxy başlığa göre, backend gövdeye göre tekilleştirirse
    aynı niyet için iki ayrı öneri oluşabilir.
    """
    if idempotency_key and idempotency_key != request.idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key başlığı ile gövdedeki idempotency_key uyuşmuyor.",
        )

    # Kim adına öneri hazırlandığı, token varsa token'dan belirlenir. Gövdedeki
    # user_id'ye güvenmek, herhangi birinin bir başkasının adına öneri
    # oluşturup o kişinin emir listesinde görünmesine izin verirdi.
    #
    # Token yoksa gövdedeki değer korunur: `mcp` bu uç noktayı kullanıcı
    # JWT'siyle değil, servis kimliğiyle çağırır ve kimin adına çalıştığını
    # gövdede bildirir.
    if authenticated_user_id and request.user_id != authenticated_user_id:
        raise HTTPException(
            status_code=403,
            detail="Bir başkası adına işlem önerisi hazırlanamaz.",
        )

    # Resolve what the user actually typed before validating. "THYAO",
    # "thyao", "THYAO.IS" and "Türk Hava Yolları" all name the same
    # instrument; refusing the ones that are not the canonical spelling is
    # what turned an ordinary buy order into REJECTED_VALIDATION.
    body = request.model_dump()
    raw_symbol = (body.get("instrument") or {}).get("symbol")
    # strict: no fuzzy neighbour on the money path. Resolution accepts
    # abbreviations and unaccented names everywhere ("thy", "turk hava
    # yollari"), but a typo like "aselsn" must not quietly become an ASELS
    # order. Reads may guess; a trade may not.
    product = (
        market_service.resolve_symbol(db, raw_symbol, strict=True) if raw_symbol else None
    )
    # When the name does not resolve, say THAT -- and offer what it might have
    # been. Without this the raw text flowed on as the symbol, no price was
    # found for it, and the blocker read "Fiyat bilgisi bulunamayan enstrüman:
    # aple" -- blaming the price for a name that was never recognised.
    # Suggestions only: strict mode still refuses to pick one, because a
    # misread ticker on the money path buys the wrong company.
    symbol_suggestions: list[str] = []
    if raw_symbol and product is None:
        symbol_suggestions = [
            candidate.symbol
            for candidate in market_service.resolve_candidates(db, raw_symbol)
        ]

    # Whose portfolio and cash this proposal is measured against. The
    # authenticated identity wins; `mcp` calls with a service identity and
    # names the user in the body.
    owner_id = authenticated_user_id or request.user_id

    # A proposal needs a real owner, and "anonymous" is not one.
    #
    # The chat degrades an expired token to an anonymous session so general
    # questions keep working (core/deps.py). That is right for READING and
    # wrong here: the orchestrator then names the user as "anonymous", the
    # account lookup below falls through to the shared DEMO account, and the
    # proposal is priced against a portfolio that is not the caller's. It is
    # then stored with user_id="anonymous", which the confirm endpoint's
    # ownership check can never match -- so the user is shown an Onayla button
    # that is guaranteed to 404. Refuse at the point the bad row would be
    # created.
    if owner_id in (None, "", "anonymous"):
        raise HTTPException(
            status_code=401,
            detail="Oturum doğrulanamadı. İşlem hazırlamak için tekrar giriş yapın.",
        )

    # No demo fallback here: `account()` returns the shared demo account for a
    # caller it cannot place, which is fine for reading and wrong for pricing
    # a trade.
    owner = market_service.account(db, user_id=owner_id, allow_demo_fallback=False)

    # The caller's own account, when they did not name one. `source_account_id`
    # was previously stored without ever being validated, so the chat asked for
    # an id, accepted "1", and used it for nothing. A user has one account of
    # each kind; making them recite its number is friction with no purpose.
    body["source_account_id"] = _resolve_source_account(
        db, body.get("source_account_id"), owner, owner_id, body.get("transaction_type")
    )

    # Rates for the funds check and for the fx block recorded on the proposal.
    # Same helper the portfolio view uses, so the two cannot disagree about
    # what a dollar is worth.
    rates = ai_service.fx_rates(market_service.latest_quotes(db))

    reference_price = None
    held_quantity = None
    currency = "TRY"
    if product is not None:
        currency = product.currency_code
        quote = market_service.latest_quotes(db, [product.symbol]).get(product.symbol)
        reference_price = quote["price"] if quote else None
        held_quantity = next(
            (
                h["quantity"]
                for h in market_service.holdings(db, user_id=owner_id)
                if h["symbol"] == product.symbol
            ),
            0.0,
        )

    proposal = ai_service.stage_transaction(
        body,
        reference_price=reference_price,
        held_quantity=held_quantity,
        resolved_symbol=product.symbol if product else None,
        symbol_suggestions=symbol_suggestions,
        currency=currency,
        available_cash=float(owner.cash_balance) if owner is not None else None,
        cash_currency=(owner.currency_code if owner is not None else "TRY") or "TRY",
        rates=rates,
    )

    # Persisted so the confirm step can be verified. Without a record,
    # "does this proposal exist and has it expired" is unanswerable and any
    # proposal_id a client invented would be honoured.
    #
    # Only confirmable proposals are stored: a rejected or incomplete one is
    # a message to the user, not something that can later be acted on.
    if proposal["status"] == "PENDING_USER_CONFIRMATION":
        _persist_proposal(
            db, request, proposal,
            owner_id=authenticated_user_id,
            # The RESOLVED account, not what the caller typed. Persisting the
            # raw value stored "1" and confirm then could not find it.
            source_account_id=body.get("source_account_id"),
        )

    return proposal


def _persist_proposal(
    db: Session,
    request: StageTransactionRequest,
    proposal: dict,
    owner_id: Optional[str] = None,
    source_account_id: Optional[str] = None,
) -> None:
    """`owner_id` doğrulanmış kimlik; yoksa gövdedeki değere düşer.

    Servis kimliğiyle gelen `mcp` çağrılarında token olmaz ve kimin adına
    çalışıldığı gövdede bildirilir; tarayıcıdan gelen çağrıda ise gövdeye
    değil token'a güvenilir.
    """
    summary = proposal.get("summary") or {}
    existing = db.get(TransactionProposal, proposal["proposal_id"])
    if existing is not None:
        # Same idempotency key, same row. A retry must not create a second
        # pending proposal for one intent, and must not resurrect a
        # confirmed one.
        return

    db.add(
        TransactionProposal(
            id=proposal["proposal_id"],
            user_id=owner_id or request.user_id,
            idempotency_key=request.idempotency_key,
            status=proposal["status"],
            transaction_type=summary.get("transaction_type") or request.transaction_type,
            symbol=summary.get("symbol"),
            quantity=summary.get("quantity"),
            source_account_id=source_account_id or request.source_account_id,
            destination_account_id=request.destination_account_id,
            order_type=summary.get("order_type") or request.order_type,
            payload=proposal,
            expires_at=datetime.fromisoformat(proposal["expires_at"].replace("Z", "+00:00")),
            audit_id=proposal["audit_id"],
        )
    )
    db.commit()


async def process_pending_transaction(proposal_id: str, email_to: str):
    """
    3 dakika bekleyip, işlemi finalize eden background task.
    """
    await asyncio.sleep(180)  # 3 minutes delay
    
    with SessionLocal() as db:
        proposal = db.get(TransactionProposal, proposal_id)
        if not proposal or proposal.status != "PENDING":
            return
            
        owner = market_service.account(db, user_id=proposal.user_id)
        if owner is None:
            return
            
        try:
            service.finalize_settlement(db, proposal, owner)
            proposal.status = "CONFIRMED"
            proposal.confirmed_at = datetime.now(timezone.utc)
            
            # --- In-App Notification Entegrasyonu ---
            # Kullanıcıya işlemin başarıyla gerçekleştiğine dair gerçek zamanlı bildirim ekliyoruz.
            quantity = float(proposal.quantity or 0)
            db.add(Notification(
                user_id=proposal.user_id,
                title="İşlem Gerçekleşti",
                description=f"{quantity} lot {proposal.symbol} {proposal.transaction_type.lower()} işleminiz başarıyla tamamlandı.",
                type="SUCCESS",
                link_url="/portfolio"
            ))
            # ----------------------------------------
            
            db.commit()
            
            if email_to:
                quantity = float(proposal.quantity or 0)
                estimate = (proposal.payload or {}).get("estimate") or {}
                total_amount = abs(float(estimate.get("net_amount", 0)))
                price = (total_amount / quantity) if quantity > 0 else 0.0
                await send_transaction_email(
                    email_to=email_to,
                    transaction_type=proposal.transaction_type,
                    asset_symbol=proposal.symbol,
                    quantity=quantity,
                    price=price,
                    total_amount=total_amount,
                    transaction_date=proposal.confirmed_at
                )
        except Exception as e:
            db.rollback()
            logging.getLogger(__name__).error("Failed to finalize transaction %s: %s", proposal_id, e)
            try:
                service.rollback_funds(db, proposal, owner)
                proposal.status = "FAILED"
                
                # --- In-App Notification Entegrasyonu ---
                # Hata durumunda (fiyat değişimi vb.) para iadesi sonrası hata bildirimi oluşturuyoruz.
                db.add(Notification(
                    user_id=proposal.user_id,
                    title="İşlem Başarısız",
                    description=f"{proposal.symbol} {proposal.transaction_type.lower()} işleminiz teknik bir nedenden ötürü gerçekleştirilemedi. Bakiyeniz iade edildi.",
                    type="ERROR",
                    link_url="/portfolio"
                ))
                # ----------------------------------------
                
                db.commit()
            except Exception as rb_e:
                db.rollback()
                logging.getLogger(__name__).error("Failed to rollback transaction %s: %s", proposal_id, rb_e)


@router.post(
    "/transactions/{proposal_id}/confirm",
    response_model=Dict[str, str],
    summary="Kullanıcının onayladığı işlem önerisini kesinleştir",
)
def confirm_transaction_proposal(
    proposal_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """
    Sohbetteki onay düğmesinin çağırdığı uç nokta.
    """
    proposal = db.get(TransactionProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Böyle bir işlem önerisi bulunamadı.")

    if proposal.user_id and proposal.user_id != user_id:
        raise HTTPException(status_code=404, detail="Böyle bir işlem önerisi bulunamadı.")

    if proposal.cancelled_at is not None:
        raise HTTPException(status_code=409, detail="Bu öneri iptal edilmiş.")

    if proposal.confirmed_at is not None or proposal.status == "PENDING":
        return {
            "proposal_id": proposal.id,
            "status": proposal.status.lower(),
            "message": f"İşlem zaten işleme alınmıştı (Öneri No: {proposal.id}).",
        }

    now = datetime.now(timezone.utc)
    expires_at = proposal.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise HTTPException(
            status_code=410,
            detail="Bu önerinin süresi doldu. Lütfen işlemi yeniden hazırlatın.",
        )

    if (proposal.transaction_type or "").upper() in ai_service.TRANSFER_TYPES:
        return _confirm_transfer(db, proposal, user_id, now)

    owner = market_service.account(db, user_id=proposal.user_id or user_id)
    if owner is None:
        raise HTTPException(
            status_code=409,
            detail="Bu işlemi uygulayacak bir yatırım hesabı bulunamadı.",
        )

    try:
        applied = service.block_funds(db, proposal, owner)
    except service.SettlementError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    proposal.status = "PENDING"
    
    # --- In-App Notification Entegrasyonu ---
    # Alım/Satım talebi alındığında kullanıcıya hemen beklemede olduğunu bildiren bir bildirim atıyoruz.
    quantity = float(proposal.quantity or 0)
    db.add(Notification(
        user_id=proposal.user_id or user_id,
        title="Talebiniz Alındı",
        description=f"{quantity} lot {proposal.symbol} {proposal.transaction_type.lower()} talebiniz sıraya alındı.",
        type="INFO",
        link_url="/portfolio"
    ))
    # ----------------------------------------
    
    db.commit()

    trade_owner_id = proposal.user_id or user_id
    user_obj = db.get(User, trade_owner_id)
    
    email_to = ""
    if user_obj and user_obj.email:
        prefs = getattr(user_obj, "notification_preferences", {}) or {}
        should_send_email = prefs.get("transactions", {}).get("email", True)
        if should_send_email:
            email_to = user_obj.email
            total_amount = abs(applied.get("cash_delta", 0.0))
            quantity = float(proposal.quantity or 0)
            price = (total_amount / quantity) if quantity > 0 else 0.0
            
            # Request received (PENDING) email
            background_tasks.add_task(
                send_transaction_request_email,
                email_to=email_to,
                transaction_type=proposal.transaction_type,
                asset_symbol=proposal.symbol,
                quantity=quantity,
                price=price, 
                total_amount=total_amount,
                transaction_date=now
            )

    # Add background task for settlement after 3 minutes
    background_tasks.add_task(
        process_pending_transaction,
        proposal_id=proposal.id,
        email_to=email_to
    )

    return {
        "proposal_id": proposal.id,
        "status": "pending",
        "message": (
            f"İşlem sıraya alındı (Öneri No: {proposal.id}). "
            f"Kalan bakiye: {applied['cash_after']:,.2f} TL."
        ),
    }


def _resolve_source_account(
    db: Session,
    requested: Optional[str],
    owner,
    owner_id: Optional[str],
    transaction_type: Optional[str],
) -> Optional[str]:
    """The account this transaction draws on.

    A transfer draws on the deposit account; a trade on the investment one.
    An id the caller supplied is honoured only if it is genuinely theirs —
    otherwise it is replaced rather than trusted, because it was never checked
    before and "1" was accepted as a real account.
    """
    from app.modules.banking import service as banking_service

    is_transfer = (transaction_type or "").upper() in ai_service.TRANSFER_TYPES

    if is_transfer:
        if requested:
            named = banking_service.find_account(db, requested)
            if named is not None and named.user_id == owner_id:
                return named.account_number
        if owner_id:
            return banking_service.ensure_account(db, owner_id).account_number
        return requested

    if requested and owner is not None and requested == owner.account_number:
        return requested
    return owner.account_number if owner is not None else requested


def _confirm_transfer(db: Session, proposal, user_id, now) -> Dict[str, str]:
    """Apply a confirmed transfer through the banking ledger.

    `banking.service.transfer` commits its own transaction (both legs plus the
    transaction row), so the proposal's status is written immediately after and
    committed separately. The ordering matters: a transfer that moved money but
    left the proposal pending can be re-read from the ledger by its reference
    number, whereas the reverse — a proposal marked confirmed with no ledger
    entry — leaves nothing to reconcile against.
    """
    from app.modules.banking import service as banking_service

    amount = ((proposal.payload or {}).get("estimate") or {}).get("net_amount")
    if amount is None:
        raise HTTPException(
            status_code=409, detail="Bu transferin tutar bilgisi eksik."
        )

    try:
        result = banking_service.transfer(
            db,
            user_id=proposal.user_id or user_id,
            source_reference=proposal.source_account_id or "",
            destination_reference=proposal.destination_account_id or "",
            amount=float(amount),
        )
    except banking_service.TransferError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    proposal.confirmed_at = now
    proposal.status = "CONFIRMED"
    db.commit()

    return {
        "proposal_id": proposal.id,
        "status": "confirmed",
        "message": (
            f"Transfer tamamlandı (Dekont No: {result['reference_number']}). "
            f"Kalan bakiye: {result['source_balance_after']:,.2f} "
            f"{result['currency']}."
        ),
    }


@router.get(
    "/products",
    response_model=List[Dict[str, Optional[str]]],
    summary="Sembol haritası (servisler arası)",
)
def list_products(db: Session = Depends(get_db)):
    """
    `ingestor` servisinin hangi sembolleri çekeceğini öğrendiği uç nokta.

    Haritayı ingestor'ın kendi konfigürasyonuna gömmek yerine buradan
    sormasının sebebi: yeni bir enstrüman eklemek bir veritabanı satırı olsun,
    ingestor'ın yeniden deploy edilmesi gerekmesin.

    `data_symbol`'ü olmayan ürünler döndürülmez; o alan boşsa "bu enstrümanı
    fiyatlama" demektir.
    """
    return [
        {
            "symbol": product.symbol,
            "data_symbol": product.data_symbol,
            "currency_code": product.currency_code,
            "market": product.market,
        }
        for product in market_service.list_products(db, only_priced=True)
    ]


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


# ---------------------------------------------------------------------------
# Hedef dağılım ve ondan sapma
#
# Hedefi KULLANICI koyuyor, sistem değil. `compliance/rules.py:SUI-001`'in
# gerekçesi: "sistem ölçüm ile kullanıcının kendi beyanını karşılaştırır, bir
# ürünün kişiye uygunluğuna karar vermez." Bir model portföy önermek o kararı
# vermek olurdu -- ve dört SPK ürün grubundan yalnızca hisse senedinin bu
# sistemde enstrümanı olduğu için önerilenin çoğu uygulanamazdı.
# ---------------------------------------------------------------------------


def _targets_for(db: Session, user_id: Optional[str]) -> dict[str, float]:
    """Okuma `service`'e taşındı: risk modülü de aynı satırları okuyor ve
    tabloyu sahibi olan modülün okuması gerekiyor."""
    return service.allocation_targets(db, user_id)


@router.get(
    "/allocation-target",
    response_model=AllocationTargetOut,
    summary="Hedef dağılımım",
)
def get_allocation_target(
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """Kullanıcının kendi belirlediği hedef ağırlıklar."""
    rows = (
        db.query(AllocationTarget)
        .filter(AllocationTarget.user_id == user_id)
        .order_by(AllocationTarget.bucket)
        .all()
        if user_id
        else []
    )
    return {
        "hasTarget": bool(rows),
        "targets": [
            {
                "bucket": row.bucket,
                "label": allocation.label_for(row.bucket),
                "targetPercent": float(row.target_percent),
            }
            for row in rows
        ],
        "updatedAt": max((row.updated_at for row in rows), default=None),
    }


@router.put(
    "/allocation-target",
    response_model=AllocationTargetOut,
    summary="Hedef dağılımı belirle",
)
def set_allocation_target(
    request: AllocationTargetRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """
    Hedef ağırlıkları tamamen değiştirir; boş liste hedefi kaldırır.

    Toplam 100 olmak ZORUNDA. Yüzde yüze tamamlanmayan bir hedef, sapma
    hesabında her kovayı aynı anda "eksik" ya da "fazla" gösterir ve
    kullanıcı hangi sayının yanlış olduğunu göremez.
    """
    seen: dict[str, float] = {}
    for item in request.targets:
        if item.bucket not in allocation.TARGETABLE:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"'{item.bucket}' hedef belirlenebilir bir kova değil; "
                    f"geçerli değerler: {', '.join(allocation.TARGETABLE)}."
                ),
            )
        if item.bucket in seen:
            raise HTTPException(
                status_code=422,
                detail=f"'{item.bucket}' için iki hedef verildi.",
            )
        seen[item.bucket] = float(item.targetPercent)

    if seen:
        total = round(sum(seen.values()), 2)
        if total != 100.0:
            raise HTTPException(
                status_code=422,
                detail=f"Hedeflerin toplamı 100 olmalı; verilen toplam {total:g}.",
            )

    db.query(AllocationTarget).filter(AllocationTarget.user_id == user_id).delete()
    now = datetime.now(timezone.utc)
    for bucket, percent in seen.items():
        db.add(AllocationTarget(
            user_id=user_id, bucket=bucket, target_percent=percent, updated_at=now
        ))
    db.commit()
    return get_allocation_target(db=db, user_id=user_id)


@router.get(
    "/allocation-drift",
    response_model=AllocationDriftOut,
    summary="Hedeften sapma",
)
def get_allocation_drift(
    db: Session = Depends(get_db),
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    """
    Ölçülen ağırlıklar ile kullanıcının kendi hedefi arasındaki fark.

    Tavsiye değil, iki olgunun çıkarması: biri portföyden ölçülüyor, diğeri
    kullanıcının kendi girdiği sayı. Hiçbir yerde ne yapılması gerektiği
    söylenmiyor -- yalnızca hedefe ulaşmak için kaç lira fark olduğu.
    """
    rows = market_service.holdings(db, user_id=user_id)
    quotes = market_service.latest_quotes(db)
    rates = ai_service.fx_rates(quotes)
    account = market_service.account(db, user_id=user_id)

    valued = [
        (row, value)
        for row, value in ((row, ai_service.holding_value(row, rates)) for row in rows)
        if value is not None
    ]
    amounts = allocation.current_amounts(
        valued, float(account.cash_balance) if account else 0.0
    )
    result = allocation.drift(amounts, _targets_for(db, user_id))
    return {
        "hasTarget": result["has_target"],
        "totalValue": result["total_value"],
        "buckets": [
            {
                "bucket": row["bucket"],
                "label": row["label"],
                "amount": row["amount"],
                "currentPercent": row["current_percent"],
                "targetPercent": row["target_percent"],
                "gapPoints": row["gap_points"],
                "gapAmount": row["gap_amount"],
            }
            for row in result["buckets"]
        ],
        "statement": result["statement"],
    }
