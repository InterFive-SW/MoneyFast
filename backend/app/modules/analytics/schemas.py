"""Portföy Analizi response shapes.

Every field here is derived from data the system already holds — positions,
candles, quotes, fundamentals and confirmed proposals. Nothing is generated,
and a figure that cannot be computed is None rather than zero: BR-02 requires
the allocation to sum to 100%, which is only meaningful if the parts are real.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AllocationSlice(BaseModel):
    label: str
    value: float
    percentage: float


class TrendPoint(BaseModel):
    date: datetime
    value: float


class BenchmarkSeries(BaseModel):
    """The index the portfolio is shown against, on the portfolio's own dates.

    Raw closes, not rescaled: the chart decides how to put two series with
    different units on one axis, and an already-normalised number would leave
    the page unable to say what the index actually did.
    """

    symbol: str
    points: List[TrendPoint] = Field(default_factory=list)


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
    #: Currency every figure below is expressed in. Without it the page had to
    #: assume, and it assumed TRY over a sum that mixed TRY and USD.
    base_currency: str = "TRY"
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
    #: None when the index has no overlapping history. A comparison line drawn
    #: from a partial overlap would show the portfolio and the index diverging
    #: on days one of them simply had no bar.
    benchmark: Optional[BenchmarkSeries] = None
    performance: PerformanceSummary
    activity: ActivitySummary

    #: Symbols excluded from the trend because they have no price history.
    #: Named rather than silently dropped — a trend computed over part of a
    #: portfolio is not the portfolio's trend.
    excluded_symbols: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ReportSection(BaseModel):
    """Raporun bir bölümü.

    `summary` KODDA kurulmuş tek cümle; ekran, PDF ve sohbet onu olduğu gibi
    okuyor. `lines` insan okuru için hazır satırlar, `rows` ise tabloyu çizen
    yapısal veri -- ikisi aynı bilgiyi taşıyor çünkü PDF satırları, ekran
    tabloyu istiyor.
    """

    key: str
    title: str
    summary: str = ""
    lines: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)


class PortfolioReport(BaseModel):
    #: Belgenin ÜRETİLDİĞİ an.
    generated_at: str
    currency_code: str = "TRY"
    #: İçindeki FİYATLARIN ait olduğu an -- `generated_at` ile aynı şey değil.
    #: Rapor, gecikmeyi söylemeyen tek yüzey olmamalı: sohbet, portföy ucu ve
    #: gösterge paneli hepsi söylüyor.
    as_of: str = ""
    is_delayed: bool = False
    #: Sağlayıcının BESLEME gecikmesi. Gözlemin yaşı DEĞİL -- ikisi bir dönem
    #: toplanıyordu ve kapalı bir borsanın son kapanışı "1095 dakika
    #: gecikmeli" diye raporlanıyordu.
    delay_minutes: int = 0
    #: Gözlemin kendisi eskidiyse. Piyasa kapalıyken normal (son kapanış),
    #: açıkken arıza işareti; ikisi de bildirilir ama yalnızca biri gecikmedir.
    is_stale: bool = False
    #: Eskiliğin sebebi, BİLİNİYORSA. "MARKET_CLOSED" ya da None. None,
    #: "sebep bilinmiyor" demek -- kapalılık iddia edilmez.
    stale_reason: Optional[str] = None
    sections: List[ReportSection] = Field(default_factory=list)
