"""Portföy Analizi — composition, not re-implementation.

Asset allocation, sector breakdown and the full risk metric suite already
exist under `investment` and `risk`. This module assembles one report from the
same sources rather than growing a second copy of the arithmetic, so the
analysis screen and the dashboard can never disagree about what the portfolio
is worth.

What is genuinely new here is the portfolio TREND: a value series reconstructed
from daily candles at today's holdings. That is a backtest of the current
basket, not a record of what the account was worth historically — the system
has no position history to draw a true one from. The distinction is surfaced in
`warnings` rather than left for the reader to assume.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.modules.investment.ai_service import _convert
from app.modules.risk import returns as risk_returns

log = logging.getLogger("moneyfast.analytics")

#: Trading days below which a volatility or drawdown figure is not reported as
#: a measurement. Matches the risk module's stance: a number from a handful of
#: bars is arithmetic, not evidence.
MIN_RELIABLE_OBSERVATIONS = 60

#: Bars pulled per symbol for the trend. About a year of trading days.
TREND_WINDOW = 260


def _percent(part: float, whole: float) -> float:
    return round((part / whole) * 100, 2) if whole else 0.0


def _normalise(slices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Force the percentages to sum to exactly 100.

    BR-02 states the allocation must always total 100%. Rounding each slice
    independently does not guarantee that — twelve positions rounded to two
    decimals landed on 100.02% — and a pie chart whose slices visibly do not
    add up undermines every other number on the screen.

    The residual goes on the LARGEST slice, where it is proportionally
    smallest and cannot flip a small holding's displayed share.
    """
    if not slices:
        return slices
    total = round(sum(entry["percentage"] for entry in slices), 2)
    residual = round(100.0 - total, 2)
    if residual:
        largest = max(slices, key=lambda entry: entry["percentage"])
        largest["percentage"] = round(largest["percentage"] + residual, 2)
    return slices


def build(
    db: Session,
    user_id: Optional[str],
    holdings: list[dict[str, Any]],
    cash: float,
    sector_map: dict[str, str],
    closes_for: Callable[[str], list[tuple[datetime, float]]],
    proposals: list[Any],
    as_of: Optional[datetime] = None,
    delay_minutes: int = 0,
    rates: Optional[dict[str, float]] = None,
    base_currency: str = "TRY",
) -> dict[str, Any]:
    """Assemble the report. Pure: every input is supplied by the router."""
    warnings: list[str] = []

    priced = [row for row in holdings if row.get("price") is not None]
    if len(priced) != len(holdings):
        missing = sorted(
            row["symbol"] for row in holdings if row.get("price") is None
        )
        warnings.append(
            "Fiyatı bulunamayan pozisyonlar değerlemeye dahil edilmedi: "
            + ", ".join(missing)
        )

    # Values in the ACCOUNT's currency, converted per holding.
    #
    # These sums used to add USD straight to TRY, so a portfolio holding AAPL,
    # MSFT and NVDA counted them at roughly 1/48th of their worth: this page
    # reported ₺404.467 while /portfolio/summary reported ₺1.087.834 for the
    # same holdings. A holding whose rate is missing is excluded and named
    # rather than converted at an invented rate.
    rates = rates or {"TRY": 1.0}
    valued, unconvertible = [], []
    for row in priced:
        try:
            market_value = _convert(
                row["quantity"] * row["price"], row.get("currency") or base_currency,
                base_currency, rates,
            )
            cost_basis = _convert(
                row["quantity"] * row["avg_cost"], row.get("currency") or base_currency,
                base_currency, rates,
            )
        except KeyError:
            unconvertible.append(row["symbol"])
            continue
        valued.append((row, market_value, cost_basis))

    if unconvertible:
        warnings.append(
            "Kuru alınamadığı için değerlemeye dahil edilmeyen pozisyonlar: "
            + ", ".join(sorted(unconvertible))
        )

    invested = sum(market_value for _, market_value, _ in valued)
    cost = sum(cost_basis for _, _, cost_basis in valued)
    total = invested + cash

    allocation = [
        {"label": "Nakit (TRY)", "value": round(cash, 2), "percentage": _percent(cash, total)}
    ]
    for row, value, _ in sorted(valued, key=lambda entry: entry[1], reverse=True):
        allocation.append(
            {
                "label": row["symbol"],
                "value": round(value, 2),
                "percentage": _percent(value, total),
            }
        )

    sectors: dict[str, float] = {}
    for row, value, _ in valued:
        # "Bilinmiyor" rather than a guess: assigning a sector by inference
        # would make the breakdown look more certain than it is.
        label = sector_map.get(row["symbol"]) or "Bilinmiyor"
        sectors[label] = sectors.get(label, 0.0) + value

    trend, excluded = _trend([row for row, _, _ in valued], closes_for)
    if excluded:
        warnings.append(
            "Fiyat geçmişi olmayan enstrümanlar trend hesabının dışında: "
            + ", ".join(excluded)
        )
    if trend:
        warnings.append(
            "Trend, bugünkü pozisyonların geçmiş fiyatlarla yeniden "
            "değerlenmesidir; hesabın geçmişteki gerçek değeri değildir."
        )

    values = [point["value"] for point in trend]
    series = risk_returns.simple_returns(values)
    drawdown = risk_returns.max_drawdown(values) if values else None

    performance = {
        "observations": len(values),
        "start_value": round(values[0], 2) if values else None,
        "end_value": round(values[-1], 2) if values else None,
        "total_return_percent": (
            round(((values[-1] / values[0]) - 1) * 100, 2)
            if len(values) >= 2 and values[0]
            else None
        ),
        "annualised_volatility": risk_returns.annualised_volatility(series),
        "max_drawdown_percent": (
            round(drawdown["value"] * 100, 2)
            if drawdown and drawdown.get("value") is not None
            else None
        ),
        "is_statistically_reliable": len(series) >= MIN_RELIABLE_OBSERVATIONS,
    }

    _normalise(allocation)

    return {
        "base_currency": base_currency,
        "as_of": as_of,
        "is_delayed": True,
        "delay_minutes": delay_minutes,
        "total_value": round(total, 2),
        "cash": round(cash, 2),
        "invested": round(invested, 2),
        "unrealised_pnl": round(invested - cost, 2),
        "unrealised_pnl_percent": (
            round(((invested - cost) / cost) * 100, 2) if cost else None
        ),
        "allocation": allocation,
        "sectors": _normalise([
            {"label": label, "value": round(value, 2), "percentage": _percent(value, invested)}
            for label, value in sorted(sectors.items(), key=lambda kv: kv[1], reverse=True)
        ]),
        "trend": trend,
        "performance": performance,
        "activity": _activity(proposals),
        "excluded_symbols": excluded,
        "warnings": warnings,
    }


def _trend(
    priced: list[dict[str, Any]], closes_for: Callable[[str], list[tuple[datetime, float]]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Portfolio value per day, from each holding's close.

    Only dates where EVERY included symbol has a bar are used. Carrying a stale
    price forward for one name would show the portfolio moving on a day that
    name did not trade, which is a fabricated data point.
    """
    per_symbol: dict[str, dict[datetime, float]] = {}
    excluded: list[str] = []

    for row in priced:
        closes = closes_for(row["symbol"])
        if len(closes) < 2:
            excluded.append(row["symbol"])
            continue
        per_symbol[row["symbol"]] = {stamp.date(): close for stamp, close in closes}

    if not per_symbol:
        return [], sorted(excluded)

    common = set.intersection(*(set(days) for days in per_symbol.values()))
    if not common:
        return [], sorted(excluded)

    quantities = {row["symbol"]: row["quantity"] for row in priced}
    trend = [
        {
            "date": datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
            "value": round(
                sum(quantities[symbol] * days[day] for symbol, days in per_symbol.items()), 2
            ),
        }
        for day in sorted(common)
    ]
    return trend, sorted(excluded)


def _activity(proposals: list[Any]) -> dict[str, Any]:
    """Realised activity from confirmed proposals — the only per-user
    transaction history that exists (FG-B-05, FG-B-08)."""
    confirmed = [p for p in proposals if (p.status or "").upper() == "CONFIRMED"]
    buys = [p for p in confirmed if (p.transaction_type or "").upper() in {"BUY", "ALIS", "ALIŞ"}]
    sells = [p for p in confirmed if (p.transaction_type or "").upper() in {"SELL", "SATIS", "SATIŞ"}]

    traded = 0.0
    for proposal in confirmed:
        estimate = (proposal.payload or {}).get("estimate") or {}
        amount = estimate.get("net_amount")
        if amount is not None:
            traded += float(amount)

    stamps = [p.confirmed_at for p in confirmed if p.confirmed_at is not None]
    return {
        "confirmed_count": len(confirmed),
        "buy_count": len(buys),
        "sell_count": len(sells),
        "total_traded_value": round(traded, 2),
        "last_transaction_at": max(stamps) if stamps else None,
    }
