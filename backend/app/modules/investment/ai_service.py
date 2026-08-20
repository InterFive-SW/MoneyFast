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


_EXCHANGE_BY_MARKET = {"BIST": "XIST", "NASDAQ": "XNAS", "NYSE": "XNYS"}


def _convert(amount: float, from_currency: str, to_currency: str, rates: dict) -> float:
    """Convert through TRY.

    An unknown currency raises rather than defaulting to 1.0: silently
    treating 100 USD as 100 TRY understates a holding by a factor of forty.
    """
    if from_currency not in rates or to_currency not in rates:
        raise KeyError(f"no FX rate for {from_currency}->{to_currency}")
    return amount * rates[from_currency] / rates[to_currency]


def fx_rates(quotes: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """Conversion rates into TRY, from the live USD/TRY quote.

    No hardcoded fallback. If the rate has not been ingested, foreign holdings
    are reported in their own currency with a warning rather than converted at
    an invented rate — a made-up exchange rate is a made-up portfolio total.
    """
    rates = {"TRY": 1.0}
    if quotes and FX_PRODUCT in quotes:
        rates["USD"] = float(quotes[FX_PRODUCT]["price"])
    return rates


def build_portfolio(
    user_id: str,
    holdings: Optional[List[Dict[str, Any]]] = None,
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

    live_as_of, live_delay, live_is_delayed = freshness or (None, 0, False)

    rows: List[Dict[str, Any]] = []
    unpriced: List[str] = []
    unconvertible: List[str] = []

    for holding in holdings:
        # Every instrument in this universe is a listed share; index and FX
        # rows are not holdings.
        if asset_classes and "EQUITY" not in asset_classes:
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
                "asset_class": "EQUITY",
                "exchange": _EXCHANGE_BY_MARKET.get(holding.get("market") or "", "XIST"),
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
        "base_currency": base_currency,
        "positions": rows,
        "totals": {
            "total_market_value": round(total_market_value, 2),
            "total_cost_basis": round(total_cost_basis, 2),
            "total_unrealized_pnl": round(total_market_value - total_cost_basis, 2),
            "position_count": len(rows),
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
) -> Optional[Dict[str, Any]]:
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
        "fx": None,
    }


def stage_transaction(
    request: Dict[str, Any],
    reference_price: Optional[float] = None,
    held_quantity: Optional[float] = None,
    resolved_symbol: Optional[str] = None,
    currency: str = "TRY",
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
