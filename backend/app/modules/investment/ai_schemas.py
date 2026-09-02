"""Request/response models for the AI-facing investment endpoints.

Separate from `schemas.py` on purpose. `schemas.py` serves the React frontend
and uses camelCase field names shaped for rendering; these models serve the
MCP tool server and are frozen against "MCP Tools Interface Definitions v2.1".
The two have different owners and change for different reasons, so merging
them would couple a UI tweak to a tool contract.

Field names here are snake_case because that is what the contract specifies.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

ASSET_CLASSES = (
    "EQUITY", "ETF", "MUTUAL_FUND", "BOND", "FX",
    "COMMODITY", "CRYPTO", "DEPOSIT", "DERIVATIVE",
)


class PositionOut(BaseModel):
    symbol: str
    isin: Optional[str] = None
    name: str
    asset_class: str
    #: ISO 10383 işlem yeri kodu, ya da None. Bir dönem zorunluydu ve
    #: eşleşmeyen her piyasa "XIST" olarak dolduruluyordu; döviz paritelerinin
    #: ve altının merkezî bir işlem yeri yok, dolayısıyla onlar ajana
    #: "Borsa İstanbul'da işlem görüyor" diye gidiyordu. MCP sözleşmesi bu
    #: alan için zaten None bekliyor.
    exchange: Optional[str] = None
    quantity: float
    avg_cost: float
    instrument_currency: str
    last_price: float
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    weight: float
    available_quantity: float
    opened_at: str


class PortfolioTotals(BaseModel):
    #: Cash and the all-in total, added in contract v2.3. Optional so a caller
    #: whose account cannot be resolved gets None rather than a fabricated 0 —
    #: a zero balance is a claim, and the wrong one.
    cash_balance: Optional[float] = None
    total_value: Optional[float] = None
    total_market_value: float
    total_cost_basis: float
    total_unrealized_pnl: float
    position_count: int


class PortfolioPositionsOut(BaseModel):
    """Every field the v2.1 contract reads.

    `as_of`, `source` and `is_delayed` are not optional: the MCP client's
    `freshness()` guard raises ContractViolationError without them, and every
    user-facing figure derived from this payload must be attributable.
    """

    as_of: str
    source: str
    is_delayed: bool
    delay_minutes: int
    base_currency: str
    positions: List[PositionOut]
    totals: PortfolioTotals
    warnings: List[str] = Field(default_factory=list)


class Instrument(BaseModel):
    symbol: Optional[str] = None
    isin: Optional[str] = None
    exchange: Optional[str] = None
    asset_class: Optional[str] = None


class NotionalAmount(BaseModel):
    amount: float
    currency: str = "TRY"


class StageTransactionRequest(BaseModel):
    user_id: str
    transaction_type: str
    #: Optional: the backend resolves the caller's own account. It was
    #: required, which is why the chat interrogated users for an id it then
    #: never validated — "1" was accepted and used for nothing.
    source_account_id: Optional[str] = None
    idempotency_key: str
    instrument: Optional[Instrument] = None
    quantity: Optional[float] = None
    notional_amount: Optional[NotionalAmount] = None
    destination_account_id: Optional[str] = None
    beneficiary: Optional[Dict[str, Any]] = None
    order_type: str = "MARKET"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "DAY"
    assumptions: List[str] = Field(default_factory=list)


class CostEstimate(BaseModel):
    gross_amount: float
    net_amount: float
    currency: str
    # INDICATIVE obliges the orchestrator to disclose that the executed price
    # will differ. FIRM removes that obligation, so it is never the default.
    price_certainty: Literal["FIRM", "INDICATIVE"] = "INDICATIVE"
    reference_price: Optional[float] = None
    fees: List[Dict[str, Any]] = Field(default_factory=list)
    taxes: List[Dict[str, Any]] = Field(default_factory=list)
    fx: Optional[Dict[str, Any]] = None


class StageTransactionOut(BaseModel):
    proposal_id: str
    status: Literal[
        "PENDING_USER_CONFIRMATION", "REJECTED_VALIDATION", "REQUIRES_ADDITIONAL_INPUT"
    ]
    expires_at: str
    # A contract assertion, not a setting. The MCP layer refuses to present a
    # proposal where this is anything other than True, because a proposal that
    # reaches the user without a confirmation step is indistinguishable from a
    # completed order.
    confirmation_required: Literal[True] = True
    summary: Dict[str, Any] = Field(default_factory=dict)
    estimate: Optional[CostEstimate] = None
    impact: Optional[Dict[str, Any]] = None
    blockers: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    disclosures: List[str] = Field(default_factory=list)
    audit_id: str
