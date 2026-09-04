"""Projection of stored holdings onto the MCP v2.1 contract.

Two jobs:

1. Turn `investment.portfolio_positions` plus the current quotes into a
   contract-shaped portfolio snapshot. The dashboard reads the same rows
   through the same service, so the two surfaces cannot disagree about what
   the user holds or what it is worth.
2. Stage transaction proposals. Staging only: nothing here places, routes, or
   settles an order.

Pure functions of their arguments — the caller supplies holdings and quotes.
That keeps this module free of database concerns and unit-testable without a
session, and it is why the freshness of a payload always describes the data
that was actually passed in.
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


#: Product symbol carrying the USD/TRY rate. Foreign holdings are converted
#: through it, so the chatbot and the dashboard use one number by construction.
FX_PRODUCT = "USDTRY"

#: Every quoted currency pair we can convert through, keyed by the currency it
#: prices. EURTRY is ingested and quoted but was never read here, so a
#: EUR-denominated instrument raised KeyError in `_convert` and dropped out of
#: every total in silence.
FX_PRODUCTS = {"USD": "USDTRY", "EUR": "EURTRY"}

SUPPORTED_BASE_CURRENCIES = frozenset({"TRY", "USD"})

#: The one custody account in this build. Positions hang off it.
DEMO_ACCOUNT = "TR-DEMO-0001"

VALUATION_SOURCE = "YFINANCE_DELAYED"

PROPOSAL_TTL_MINUTES = 15

#: Emitted verbatim alongside every staged proposal.
STAGING_DISCLOSURES = [
    "Bu bir işlem önerisidir; onaylanana kadar hiçbir emir iletilmemiştir.",
    "Belirtilen tutarlar gösterge niteliğindedir; gerçekleşen fiyat farklı olabilir.",
    "Yatırım kararlarınız kendi sorumluluğunuzdadır.",
]

BUY_TYPES = frozenset({"BUY", "ALIS", "ALIŞ"})
SELL_TYPES = frozenset({"SELL", "SATIS", "SATIŞ"})
TRANSFER_TYPES = frozenset({"TRANSFER", "EFT", "HAVALE"})
KNOWN_TRANSACTION_TYPES = BUY_TYPES | SELL_TYPES | TRANSFER_TYPES

#: Commission on securities orders, as a fraction of gross. A dummy figure,
#: labelled as such in the estimate.
COMMISSION_RATE = 0.0015
BSMV_RATE = 0.05  # levied on the commission, not on the notional


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


#: Piyasa -> ISO 10383 işlem yeri kodu. Yalnızca gerçekten bir borsada işlem
#: gören enstrümanlar için: döviz paritelerinin ve altının merkezî bir işlem
#: yeri yok, dolayısıyla burada karşılıkları da yok.
#:
#: Eşleşmeyen piyasa NONE döner, "XIST" DEĞİL. Varsayılan "XIST"ti ve USDTRY
#: ile XAUUSD ajana "Borsa İstanbul'da işlem görüyor" diye gidiyordu -- MCP
#: sözleşmesinin kendisi bu alan için "provider has not classified the
#: instrument" durumunda None bekliyor. Bilinmeyeni bir olguya çevirmek,
#: kurun yokluğunda 1.0 varsaymakla aynı hata.
_EXCHANGE_BY_MARKET = {"BIST": "XIST", "NASDAQ": "XNAS", "NYSE": "XNYS"}

#: Product type to the contract's asset_class vocabulary.
_ASSET_CLASSES = {
    "stock": "EQUITY",
    "fx": "FX",
    "commodity": "COMMODITY",
    "index": "INDEX",
    "fund": "FUND",
    "bond": "FIXED_INCOME",
}


def _convert(amount: float, from_currency: str, to_currency: str, rates: dict) -> float:
    """Convert through TRY.

    An unknown currency raises rather than defaulting to 1.0: silently
    treating 100 USD as 100 TRY understates a holding by a factor of forty.
    """
    if from_currency not in rates or to_currency not in rates:
        raise KeyError(f"no FX rate for {from_currency}->{to_currency}")
    return amount * rates[from_currency] / rates[to_currency]


def holding_value(
    row: Dict[str, Any],
    rates: Dict[str, float],
    base_currency: str = "TRY",
    field: str = "price",
) -> Optional[float]:
    """One holding's value in `base_currency`, or None when unconvertible.

    Every surface that totals a portfolio needs this, and each used to inline
    its own version. Two of them bucketed by `market == "BIST"` and multiplied
    everything else by the USD rate — right only for as long as the only
    foreign market was American. The rest simply added USD to TRY.

    None rather than a fallback: a holding priced in a currency we have no rate
    for is excluded and reported, never converted at an invented rate.
    """
    price = row.get(field)
    if price is None:
        return None
    try:
        return _convert(
            float(row["quantity"]) * float(price),
            row.get("currency") or base_currency,
            base_currency,
            rates,
        )
    except KeyError:
        return None


def fx_rates(quotes: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """Conversion rates into TRY, from the live USD/TRY quote.

    No hardcoded fallback. If the rate has not been ingested, foreign holdings
    are reported in their own currency with a warning rather than converted at
    an invented rate — a made-up exchange rate is a made-up portfolio total.
    """
    rates = {"TRY": 1.0}
    for currency, symbol in FX_PRODUCTS.items():
        quote = (quotes or {}).get(symbol)
        if quote and quote.get("price") is not None:
            rates[currency] = float(quote["price"])
    return rates


def build_portfolio(
    user_id: str,
    holdings: Optional[List[Dict[str, Any]]] = None,
    cash_balance: Optional[float] = None,
    account_ids: Optional[List[str]] = None,
    asset_classes: Optional[List[str]] = None,
    include_closed: bool = False,
    base_currency: str = "TRY",
    valuation_mode: str = "LAST_CLOSE",
    quotes: Optional[Dict[str, Any]] = None,
    freshness: Optional[Tuple[Any, int, bool]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Project stored holdings onto the contract. Returns (payload, warnings).

    `holdings` comes from `market_service.holdings()`; each row already carries
    the live price. Everything derived — market value, cost basis, P&L, weight
    — is computed here rather than read from a stored column, so a position can
    never display a total that disagrees with its own price.
    """
    warnings: List[str] = []
    rates = fx_rates(quotes)
    holdings = holdings or []

    if account_ids:
        # The contract is explicit: unentitled or unknown accounts are omitted
        # and reported in warnings, never raised. Raising would turn a partial
        # answer into no answer.
        unknown = [a for a in account_ids if a != DEMO_ACCOUNT]
        if unknown:
            warnings.append(
                "Şu hesaplar bulunamadı veya erişim yetkisi yok, sonuçlara dahil edilmedi: "
                + ", ".join(unknown)
            )
        if DEMO_ACCOUNT not in account_ids:
            holdings = []

    if include_closed:
        warnings.append(
            "Kapatılmış pozisyonlar bu ortamda saklanmıyor; yalnızca açık pozisyonlar döndürüldü."
        )

    live_as_of, live_delay, live_is_delayed, live_is_stale = (
        freshness or (None, 0, False, False)
    )

    rows: List[Dict[str, Any]] = []
    unpriced: List[str] = []
    unconvertible: List[str] = []

    for holding in holdings:
        # Every instrument in this universe is a listed share; index and FX
        # rows are not holdings.
        # The instrument's real class, not a constant. This filter used to
        # compare every position against "EQUITY", so asking for FX returned
        # nothing and asking for equities returned gold.
        asset_class = _ASSET_CLASSES.get(
            (holding.get("product_type") or "").lower(), "EQUITY"
        )
        if asset_classes and asset_class not in asset_classes:
            continue

        symbol = holding["symbol"]
        price = holding.get("price")
        if price is None:
            # No quote yet. Omitted rather than priced at zero, which would
            # render as a holding that lost all its value.
            unpriced.append(symbol)
            continue

        currency = holding.get("currency") or "TRY"
        quantity = float(holding["quantity"])
        avg_cost = float(holding["avg_cost"])

        try:
            market_value = _convert(quantity * float(price), currency, base_currency, rates)
            cost_basis = _convert(quantity * avg_cost, currency, base_currency, rates)
        except KeyError:
            # The FX rate has not been ingested. Reporting the holding at an
            # invented rate would put a fabricated number in a portfolio total.
            unconvertible.append(symbol)
            continue

        rows.append(
            {
                "symbol": symbol,
                "isin": None,
                "name": holding.get("name") or symbol,
                # From the product, not a constant. Every position used to
                # report EQUITY, including FX pairs and gold.
                "asset_class": asset_class,
                # Feeds the risk engine's sector bucketing, which reported
                # every portfolio as 100% UNCLASSIFIED while this was absent.
                "sector": holding.get("sector"),
                "market": holding.get("market"),
                "exchange": _EXCHANGE_BY_MARKET.get(holding.get("market") or ""),
                "quantity": quantity,
                "avg_cost": avg_cost,
                "instrument_currency": currency,
                "last_price": float(price),
                "market_value": round(market_value, 2),
                "cost_basis": round(cost_basis, 2),
                "unrealized_pnl": round(market_value - cost_basis, 2),
                "unrealized_pnl_pct": (
                    round((market_value - cost_basis) / cost_basis, 6) if cost_basis else 0.0
                ),
                "weight": 0.0,
                "available_quantity": quantity,
                "opened_at": _iso(holding["opened_at"]) if holding.get("opened_at") else "",
            }
        )

    if unpriced:
        warnings.append(
            "Şu enstrümanlar için güncel fiyat alınamadı ve toplamlara dahil edilmedi: "
            + ", ".join(sorted(unpriced))
        )
    if unconvertible:
        warnings.append(
            f"Kur bilgisi ({FX_PRODUCT}) alınamadığı için şu yabancı para pozisyonları "
            "dönüştürülemedi ve toplamlara dahil edilmedi: " + ", ".join(sorted(unconvertible))
        )

    total_market_value = sum(row["market_value"] for row in rows)
    total_cost_basis = sum(row["cost_basis"] for row in rows)
    for row in rows:
        row["weight"] = (
            round(row["market_value"] / total_market_value, 6) if total_market_value else 0.0
        )

    payload = {
        # Freshness describes the prices actually used: the provider's own
        # timestamp, not now(). A delayed price with a fresh stamp is exactly
        # the misrepresentation the contract forbids.
        "as_of": _iso(live_as_of) if live_as_of else _iso(_now()),
        "source": VALUATION_SOURCE,
        "is_delayed": live_is_delayed,
        "delay_minutes": live_delay,
        # Gözlem ESKİ mi -- beslemenin gecikmesinden ayrı bir şey. Piyasa
        # kapalıyken normal (son kapanış), açıkken arıza işareti.
        "is_stale": live_is_stale,
        "base_currency": base_currency,
        "positions": rows,
        "totals": {
            "total_market_value": round(total_market_value, 2),
            "total_cost_basis": round(total_cost_basis, 2),
            "total_unrealized_pnl": round(total_market_value - total_cost_basis, 2),
            "position_count": len(rows),
            # Cash, added in contract v2.3. Without it the assistant could not
            # answer "bakiyem ne kadar" at all: it saw only position values, so
            # it either quoted the market value as if it were a balance or
            # said the figure was not in its data.
            "cash_balance": round(cash_balance, 2) if cash_balance is not None else None,
            "total_value": (
                round(total_market_value + cash_balance, 2)
                if cash_balance is not None
                else None
            ),
        },
        "warnings": warnings,
    }
    return payload, warnings


def _proposal_id(idempotency_key: str) -> str:
    """Derive the id from the key so a retry re-reads the same proposal.

    A retried staging call that mints a second proposal is the failure this
    endpoint most needs to avoid: the user would see two pending orders for
    one intent.
    """
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"PROP-{digest[:16].upper()}"


def _estimate(
    transaction_type: str,
    quantity: Optional[float],
    notional_amount: Optional[Dict[str, Any]],
    reference_price: Optional[float],
    limit_price: Optional[float],
    currency: str,
    settlement_currency: str = "TRY",
    rates: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Cost of the trade in the INSTRUMENT's currency, plus the rate to the
    account's.

    The two currencies are kept apart deliberately. AAPL costs USD; the account
    holds TRY. Collapsing them was the bug that made a 15.098 TL purchase debit
    315 TL and a 226.468 TL sale credit 4.723 TL.
    """
    price = limit_price if limit_price is not None else reference_price

    if notional_amount:
        gross = float(notional_amount.get("amount", 0.0))
        currency = notional_amount.get("currency", currency)
    elif quantity is not None and price is not None:
        gross = quantity * price
    else:
        # Nothing to price. Returning a zeroed estimate would render as a
        # free trade.
        return None

    if transaction_type.upper() in TRANSFER_TYPES:
        # A transfer is not a brokerage order. Charging it commission and BSMV
        # priced a 200 TL transfer at 200,30 TL and labelled it a securities
        # sale; the banking module owns the transfer fee.
        return {
            "gross_amount": round(gross, 2),
            "net_amount": round(gross, 2),
            "currency": currency,
            "price_certainty": "INDICATIVE",
            "reference_price": None,
            "fees": [],
            "taxes": [],
            "fx": _fx_block(currency, settlement_currency, rates),
        }

    commission = round(gross * COMMISSION_RATE, 2)
    bsmv = round(commission * BSMV_RATE, 2)
    is_sell = transaction_type.upper() in SELL_TYPES
    net = gross - commission - bsmv if is_sell else gross + commission + bsmv

    return {
        "gross_amount": round(gross, 2),
        "net_amount": round(net, 2),
        "currency": currency,
        # FIRM would tell the orchestrator it may present this as the price
        # the user will pay. Nothing in this system can promise that.
        "price_certainty": "INDICATIVE",
        "reference_price": price,
        "fees": [{"type": "COMMISSION", "amount": commission, "currency": currency}],
        "taxes": [{"type": "BSMV", "amount": bsmv, "currency": currency}],
        # The rate this trade settles at, recorded ON the proposal. Settlement
        # must not re-fetch it: the user approved a cost computed at this rate,
        # and a rate that moved between staging and confirming would silently
        # change the amount they agreed to.
        "fx": _fx_block(currency, settlement_currency, rates),
    }


def _fx_block(
    from_currency: str,
    to_currency: str,
    rates: Optional[Dict[str, float]],
) -> Optional[Dict[str, Any]]:
    """The conversion applied when the instrument is not priced in the
    account's currency. None when no conversion is needed."""
    if from_currency == to_currency:
        return None
    if not rates:
        return None
    try:
        rate = _convert(1.0, from_currency, to_currency, rates)
    except KeyError:
        return None
    return {
        "rate": round(rate, 6),
        "from_currency": from_currency,
        "to_currency": to_currency,
    }


def stage_transaction(
    request: Dict[str, Any],
    reference_price: Optional[float] = None,
    held_quantity: Optional[float] = None,
    resolved_symbol: Optional[str] = None,
    symbol_suggestions: Optional[list[str]] = None,
    currency: str = "TRY",
    available_cash: Optional[float] = None,
    cash_currency: str = "TRY",
    rates: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Validate and stage. Never executes; never returns a PASS by default.

    `reference_price`, `held_quantity` and `resolved_symbol` are supplied by
    the router after a database lookup, so this stays a pure function. The
    resolved symbol matters: a user types "thyao" or "Türk Hava Yolları", and
    refusing those was why an ordinary buy order came back as
    REJECTED_VALIDATION.
    """
    transaction_type = str(request.get("transaction_type", "")).upper()
    instrument = request.get("instrument") or {}
    symbol = instrument.get("symbol")
    quantity = request.get("quantity")
    notional = request.get("notional_amount")
    order_type = str(request.get("order_type", "MARKET")).upper()

    blockers: List[str] = []
    missing_fields: List[str] = []
    warnings: List[str] = []

    if transaction_type not in KNOWN_TRANSACTION_TYPES:
        blockers.append(f"Desteklenmeyen işlem türü: {transaction_type or '(boş)'}")

    is_securities_order = transaction_type in BUY_TYPES | SELL_TYPES

    if is_securities_order and not symbol:
        missing_fields.append("instrument.symbol")
    if quantity is None and notional is None:
        missing_fields.append("quantity")
    if quantity is not None and quantity <= 0:
        blockers.append("Miktar sıfırdan büyük olmalıdır.")

    if transaction_type in TRANSFER_TYPES and not request.get("destination_account_id"):
        missing_fields.append("destination_account_id")

    if resolved_symbol:
        symbol = resolved_symbol
    if is_securities_order and symbol and reference_price is None:
        if resolved_symbol is None:
            # The NAME failed, not the price. Reporting a missing price for
            # "aple" told the user their data was unavailable when in fact
            # nothing by that name exists.
            if symbol_suggestions:
                # "A, B veya C" -- not "A veya B veya C", which reads like a
                # machine listing rather than a question a person would ask.
                names = symbol_suggestions[:3]
                listed = names[0] if len(names) == 1 else (
                    ", ".join(names[:-1]) + " veya " + names[-1]
                )
                blockers.append(
                    f"«{symbol}» diye bir enstrüman bulunamadı. "
                    f"{listed} mı demek istediniz?"
                )
            else:
                blockers.append(f"«{symbol}» diye bir enstrüman bulunamadı.")
        else:
            blockers.append(f"Fiyat bilgisi bulunamayan enstrüman: {symbol}")

    # A sell is checked against what is actually sellable. Staging a sell for
    # more than the user holds would present an impossible order as pending.
    if transaction_type in SELL_TYPES and symbol and quantity is not None:
        held = held_quantity or 0.0
        if quantity > held:
            blockers.append(
                f"Satılabilir miktar yetersiz: {symbol} için {held:g} adet mevcut, "
                f"{quantity:g} adet talep edildi."
            )

    # The buy-side counterpart, which did not exist: a purchase was staged
    # regardless of the balance, so an unaffordable order sat "pending
    # confirmation" until confirm refused it. İK-07 states the rule for
    # transfers -- balance must cover amount plus fee -- and a purchase is the
    # same shape. Fees are included because they leave the account too.
    #
    # `available_cash is None` means the caller could not determine a balance
    # (no account resolved). Blocking then would refuse every trade over a
    # lookup failure, so the check is skipped and confirm re-checks anyway.
    if (
        transaction_type in BUY_TYPES
        and available_cash is not None
        and quantity is not None
        and reference_price is not None
    ):
        provisional = _estimate(
            transaction_type,
            quantity,
            notional,
            reference_price,
            request.get("limit_price"),
            currency,
            settlement_currency=cash_currency,
            rates=rates,
        )
        # Convert into the ACCOUNT's currency before comparing. Comparing a USD
        # cost against a TRY balance made a foreign purchase look ~48x cheaper
        # than it is, which is how an unaffordable order passed the check.
        try:
            needed = _convert(
                provisional["net_amount"], provisional["currency"], cash_currency, rates or {}
            )
        except KeyError:
            # No rate ingested. Refusing costs the user one retry; guessing at
            # 1.0 would let them buy a 15.000 TL position for 315 TL.
            blockers.append(
                f"{provisional['currency']}/{cash_currency} kuru şu anda alınamadığı için "
                f"bu işlemin maliyeti hesaplanamıyor."
            )
            needed = None
        if needed is not None and needed > available_cash:
            blockers.append(
                f"Bakiye yetersiz: işlem masraflarla birlikte {needed:,.2f} {cash_currency} "
                f"tutuyor, kullanılabilir bakiye {available_cash:,.2f} {cash_currency}."
            )

    if order_type in ("LIMIT", "STOP_LIMIT") and request.get("limit_price") is None:
        missing_fields.append("limit_price")
    if order_type in ("STOP", "STOP_LIMIT") and request.get("stop_price") is None:
        missing_fields.append("stop_price")

    if blockers:
        status = "REJECTED_VALIDATION"
    elif missing_fields:
        status = "REQUIRES_ADDITIONAL_INPUT"
    else:
        status = "PENDING_USER_CONFIRMATION"

    estimate = (
        _estimate(
            transaction_type,
            quantity,
            notional,
            reference_price,
            request.get("limit_price"),
            currency,
            settlement_currency=cash_currency,
            rates=rates,
        )
        if status == "PENDING_USER_CONFIRMATION"
        else None
    )

    for assumption in request.get("assumptions") or []:
        # Surfaced as warnings so the orchestrator, which must disclose every
        # assumption to the user, cannot present one silently.
        warnings.append(f"Varsayım: {assumption}")

    return {
        "proposal_id": _proposal_id(request["idempotency_key"]),
        "status": status,
        "expires_at": _iso(_now() + timedelta(minutes=PROPOSAL_TTL_MINUTES)),
        "confirmation_required": True,
        "summary": {
            "transaction_type": transaction_type,
            "symbol": symbol,
            "quantity": quantity,
            "order_type": order_type,
            "time_in_force": request.get("time_in_force", "DAY"),
            "source_account_id": request.get("source_account_id"),
            "destination_account_id": request.get("destination_account_id"),
        },
        "estimate": estimate,
        "impact": None,
        "blockers": blockers,
        "warnings": warnings,
        "missing_fields": missing_fields,
        "disclosures": list(STAGING_DISCLOSURES),
        "audit_id": str(uuid.uuid4()),
    }
