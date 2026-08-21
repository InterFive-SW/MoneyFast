"""Request/response models for POST /api/risk/calculate.

Frozen against "MCP Tools Interface Definitions v2.1". Field names are
snake_case because that is what the contract specifies; this module has no
frontend consumer.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

LOOKBACKS = ("1M", "3M", "6M", "1Y", "3Y", "5Y", "MAX")
METRICS = (
    "VOLATILITY", "MAX_DRAWDOWN", "VAR", "CVAR",
    "BETA", "SHARPE", "CONCENTRATION", "CORRELATION_MATRIX",
)


class PositionIn(BaseModel):
    """One holding. Extra keys are accepted and ignored.

    The agent passes `get_portfolio_positions["positions"]` straight through,
    so this model must tolerate the full contract shape without enumerating
    every field.
    """

    symbol: str
    quantity: float = 0.0
    market_value: float
    asset_class: str = "EQUITY"
    instrument_currency: str = "TRY"

    model_config = {"extra": "ignore"}


class RiskRequest(BaseModel):
    positions: List[PositionIn]
    lookback: str = "1Y"
    benchmark_symbol: Optional[str] = None
    metrics: Optional[List[str]] = None
    confidence_level: float = 0.95
    risk_free_rate: Optional[float] = None
    rebalance_assumption: str = "BUY_AND_HOLD"


class Window(BaseModel):
    start_date: str
    end_date: str
    observation_count: int
    frequency: str


class DataQuality(BaseModel):
    coverage: float
    excluded_symbols: List[str] = Field(default_factory=list)
    gap_filled_days: int = 0
    # Defaults False on purpose. The optimistic default would let a
    # three-observation window be presented as a firm volatility figure.
    is_statistically_reliable: bool = False


class RiskResponse(BaseModel):
    as_of: str
    source: str
    is_delayed: bool
    window: Window
    metrics: Dict[str, Any]
    assumptions: Dict[str, Any]
    data_quality: DataQuality


# ---------------------------------------------------------------------------
# The user-facing profile, for the Risk page.
#
# Distinct from RiskResponse above, which is frozen against the MCP contract
# and speaks in raw metrics. This one is shaped for a screen: a score, the
# findings behind it, and what to look at next.
# ---------------------------------------------------------------------------
class ScoreComponent(BaseModel):
    name: str
    #: The raw metric, so the UI can show what produced the sub-score.
    measured: Optional[float] = None
    weight: float
    #: 0..1, or None when the input could not be measured. Never coalesced to
    #: zero: an unmeasurable drawdown is not the same as no drawdown.
    penalty: Optional[float] = None


class RiskFinding(BaseModel):
    id: str
    title: str
    description: str
    impact: str
    #: The number the finding was derived from. A finding the user cannot
    #: trace back to a measurement is an opinion.
    value: Optional[float] = None


class RiskSuggestion(BaseModel):
    id: str
    title: str
    description: str
    actionLabel: str
    priority: str


class CashflowOut(BaseModel):
    """Income against expense, from the banking ledger.

    The page previously showed a debt-to-income ratio built from a fixture.
    There is no loan model in this system, so debt is not reported at all
    rather than invented.
    """

    period: str
    currency_code: str = "TRY"
    monthly_income: float = 0.0
    monthly_expense: float = 0.0
    #: None when there was no income to divide by — a savings rate of 0%
    #: would claim they spent everything they earned.
    savings_rate: Optional[float] = None


class RiskProfileOut(BaseModel):
    as_of: str
    #: None when nothing could be measured. Refusing to score is honest; a
    #: default of 50 is a number the user could act on.
    score: Optional[float] = None
    level: Optional[str] = None
    components: List[ScoreComponent] = Field(default_factory=list)
    findings: List[RiskFinding] = Field(default_factory=list)
    suggestions: List[RiskSuggestion] = Field(default_factory=list)
    cashflow: Optional[CashflowOut] = None
    #: The raw engine output, so nothing on the page is unverifiable.
    metrics: Dict[str, Any] = Field(default_factory=dict)
    position_count: int = 0
    warnings: List[str] = Field(default_factory=list)
