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


#: The index the trend chart is drawn against. Same default the risk module
#: measures beta and correlation with, so the picture and the numbers beside
#: it describe the same comparison.
BENCHMARK_SYMBOL = "XU100"


def _benchmark_series(
    dates: list[Any], closes_for: Callable[[str], list[tuple[datetime, float]]]
) -> Optional[dict[str, Any]]:
    """The index's closes on `dates`, or None when there is no real overlap.

    Raw closes, not rescaled: the chart decides how to put two series with
    different units on one axis, and handing it an already-normalised number
    would leave the page unable to say what the index itself did.
    """
    by_day = {
        stamp.date(): float(close) for stamp, close in closes_for(BENCHMARK_SYMBOL)
    }
    points = [
        {
            "date": datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
            "value": round(by_day[day], 4),
        }
        for day in dates
        if day in by_day
    ]
    if len(points) < 2:
        return None
    return {"symbol": BENCHMARK_SYMBOL, "points": points}


def window_limit(lookback: str = "1Y") -> int:
    """Bars to read per symbol for `lookback`, including the one the first
    return needs.

    The same arithmetic `risk.service.history_limit` does, off the same table,
    so one period selector can drive both endpoints and mean the same thing.
    It replaced a fixed 260 -- "about a year" -- while risk asked for 253, and
    the two then measured the same portfolio over different spans. With one
    series behind both, a window that is merely close was the last thing that
    could still make them disagree, and on a single screen showing both that
    difference has nowhere to hide.
    """
    return risk_returns.window_for(lookback) + 1


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

    # The same series `risk` measures. Built once, in `risk/returns.py`:
    # this page and the risk page were computing volatility and max drawdown
    # from two differently-built series and reporting different numbers for
    # one portfolio. It also fixes a currency bug this module had on its own --
    # `_trend` summed `quantity x close` with no conversion, adding dollars to
    # lira, while the allocation block three lines above converted properly.
    dates, trend_values, excluded = risk_returns.value_series(
        [
            {**row, "market_value": market_value}
            for row, market_value, _ in valued
        ],
        closes_for,
        base_currency,
    )
    trend = [
        {
            "date": datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
            "value": round(value, 2),
        }
        for day, value in zip(dates, trend_values)
    ]
    if excluded:
        # Names them AND says what their absence costs. The series ends at the
        # value of what it could measure, so with something left out the last
        # point sits below the total shown above it -- a gap the reader would
        # otherwise have to notice and explain to themselves.
        warnings.append(
            "Fiyat geçmişi yetersiz olduğu için trend hesabının dışında kalan "
            "enstrümanlar: " + ", ".join(excluded)
            + ". Grafikteki değer bu pozisyonları içermez, dolayısıyla "
            "yukarıdaki toplamın altında kalır."
        )
    if trend:
        warnings.append(
            "Trend, bugünkü pozisyonların geçmiş fiyatlarla yeniden "
            "değerlenmesidir; hesabın geçmişteki gerçek değeri değildir."
        )

    # The index on the portfolio's OWN dates. Days the index did not trade are
    # dropped rather than carried forward, so the two lines only ever meet on
    # days both actually have -- a forward-filled index shows the market flat
    # on a day it was simply closed.
    benchmark = _benchmark_series(dates, closes_for)

    values = trend_values
    series = risk_returns.simple_returns(values)
    drawdown = risk_returns.max_drawdown(values, dates) if values else None

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
        "benchmark": benchmark,
        "performance": performance,
        "activity": _activity(proposals),
        "excluded_symbols": excluded,
        "warnings": warnings,
    }


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
