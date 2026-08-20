"""Portföy Analizi response shapes.

Every field here is derived from data the system already holds — positions,
candles, quotes, fundamentals and confirmed proposals. Nothing is generated,
and a figure that cannot be computed is None rather than zero: BR-02 requires
the allocation to sum to 100%, which is only meaningful if the parts are real.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AllocationSlice(BaseModel):
    label: str
    value: float
    percentage: float


class TrendPoint(BaseModel):
    date: datetime
    value: float


class PerformanceSummary(BaseModel):
    """Portfolio-level return over the window actually covered by the data."""

    #: Trading days genuinely available, not the days requested. A 1-year
    #: window backed by 40 bars is not a 1-year measurement.
    observations: int
    start_value: Optional[float] = None
    end_value: Optional[float] = None
    total_return_percent: Optional[float] = None
    annualised_volatility: Optional[float] = None
    max_drawdown_percent: Optional[float] = None
    #: False when the window is too thin to say anything. The UI must not
    #: present a number computed from a handful of bars as a measurement.
    is_statistically_reliable: bool = False


class ActivitySummary(BaseModel):
    """Realised activity, from confirmed transaction proposals."""

    confirmed_count: int = 0
    buy_count: int = 0
    sell_count: int = 0
    total_traded_value: float = 0.0
    last_transaction_at: Optional[datetime] = None


class PortfolioAnalysis(BaseModel):
    as_of: Optional[datetime] = None
    is_delayed: bool = True
    delay_minutes: int = 0

    total_value: float = 0.0
    cash: float = 0.0
    invested: float = 0.0
    unrealised_pnl: float = 0.0
    unrealised_pnl_percent: Optional[float] = None

    allocation: List[AllocationSlice] = Field(default_factory=list)
    sectors: List[AllocationSlice] = Field(default_factory=list)
    trend: List[TrendPoint] = Field(default_factory=list)
    performance: PerformanceSummary
    activity: ActivitySummary

    #: Symbols excluded from the trend because they have no price history.
    #: Named rather than silently dropped — a trend computed over part of a
    #: portfolio is not the portfolio's trend.
    excluded_symbols: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
