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
