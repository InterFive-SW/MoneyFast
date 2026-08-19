"""Database-backed investment queries and financial calculations.

The backend currently uses synchronous SQLAlchemy sessions, so these functions
are deliberately synchronous. FastAPI, agents, and MCP tools can all inject the
same session/repository without creating another connection system.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol, TypeAlias
from uuid import UUID

from sqlalchemy import Uuid, column, select, table
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.investment.models import (
    InvestmentAccount,
    InvestmentOrder,
    InvestmentProduct,
    InvestmentTrade,
    MarketQuote,
    PortfolioPosition,
)
from app.modules.investment.schemas import (
    AssetAllocationItem,
    InvestmentBalance,
    InvestmentBreakdown,
    InvestmentTransaction,
    Order,
    Position,
)

UserId: TypeAlias = str | UUID
ZERO = Decimal(0)
HUNDRED = Decimal(100)
ACTIVE_STATUS = "active"

# A lightweight SQLAlchemy Core reference avoids importing the auth module's
# ORM model, as required by the project's module-boundary rules.
AUTH_USERS = table(
    "users",
    column("id", Uuid()),
    column("national_id"),
    column("status"),
    schema="auth",
)

_US_MARKETS = frozenset({"NASDAQ", "NYSE", "AMEX", "US"})
_ASSET_CLASS_NAMES = {
    "stock": "Hisse Senedi",
    "fund": "Yatırım Fonu",
    "bond": "Tahvil",
    "gold": "Altın",
    "commodity": "Emtia",
    "cash": "Nakit",
}
_ASSET_CLASS_COLORS = {
    "stock": "#10b981",
    "fund": "#8b5cf6",
    "bond": "#3b82f6",
    "gold": "#f59e0b",
    "commodity": "#f97316",
    "cash": "#94a3b8",
}


class InvestmentUserNotFound(LookupError):
    """Raised when ``auth.users`` has no row for the requested identifier."""


class InvestmentDataUnavailable(RuntimeError):
    """Raised when a truthful result cannot be calculated from stored data."""


class InvestmentDatabaseError(RuntimeError):
    """Raised when an investment database read fails."""


@dataclass(frozen=True)
class AccountRecord:
    currency_code: str | None
    cash_balance: Decimal | None


@dataclass(frozen=True)
class HoldingRecord:
    symbol: str
    product_type: str
    market: str | None
    currency_code: str | None
    quantity: Decimal
    average_buy_price: Decimal
    cached_price: Decimal | None
    cached_price_updated_at: datetime | None
    quote_price: Decimal | None
    quote_change_amount: Decimal | None
    quote_change_percent: Decimal | None
    quote_timestamp: datetime | None
    quote_source: str | None


@dataclass(frozen=True)
class TradeRecord:
    trade_number: str
    order_number: str
    symbol: str
    currency_code: str | None
    side: str
    quantity: Decimal
    price: Decimal
    commission: Decimal | None
    tax: Decimal | None
    total_amount: Decimal
    executed_at: datetime


@dataclass(frozen=True)
class OrderRecord:
    order_number: str
    symbol: str
    currency_code: str | None
    side: str
    quantity: Decimal
    executed_quantity: Decimal | None
    limit_price: Decimal | None
    stop_price: Decimal | None
    average_execution_price: Decimal | None
    status: str | None
    submitted_at: datetime | None


@dataclass(frozen=True)
class PriceState:
    price: Decimal | None
    as_of: datetime | None
    source: str | None
    uses_quote: bool


class InvestmentRepository(Protocol):
    """Read operations needed by the service and replaceable in unit tests."""

    def user_exists(self, user_id: UUID) -> bool: ...

    def resolve_active_user_id(self, national_id: str) -> UUID | None: ...

    def get_accounts(self, user_id: UUID) -> list[AccountRecord]: ...

    def get_holdings(self, user_id: UUID) -> list[HoldingRecord]: ...

    def get_trades(self, user_id: UUID) -> list[TradeRecord]: ...

    def get_orders(self, user_id: UUID) -> list[OrderRecord]: ...


class SQLAlchemyInvestmentRepository:
    """SQLAlchemy implementation backed by tables from ``intertech.sql``."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def user_exists(self, user_id: UUID) -> bool:
        statement = (
            select(AUTH_USERS.c.id)
            .where(
                AUTH_USERS.c.id == user_id,
                AUTH_USERS.c.status == ACTIVE_STATUS,
            )
            .limit(1)
        )
        return self.db.scalar(statement) is not None

    def resolve_active_user_id(self, national_id: str) -> UUID | None:
        statement = (
            select(AUTH_USERS.c.id)
            .where(
                AUTH_USERS.c.national_id == national_id,
                AUTH_USERS.c.status == ACTIVE_STATUS,
            )
            .limit(1)
        )
        return self.db.scalar(statement)

    def get_accounts(self, user_id: UUID) -> list[AccountRecord]:
        statement = (
            select(InvestmentAccount.currency_code, InvestmentAccount.cash_balance)
            .where(
                InvestmentAccount.user_id == user_id,
                InvestmentAccount.status == ACTIVE_STATUS,
            )
            .order_by(InvestmentAccount.account_number)
        )
        return [
            AccountRecord(
                currency_code=row.currency_code.upper() if row.currency_code else None,
                cash_balance=row.cash_balance,
            )
            for row in self.db.execute(statement)
        ]

    def get_holdings(self, user_id: UUID) -> list[HoldingRecord]:
        latest_price = (
            select(MarketQuote.price)
            .where(MarketQuote.product_id == PortfolioPosition.product_id)
            .order_by(MarketQuote.market_timestamp.desc(), MarketQuote.id.desc())
            .limit(1)
            .correlate(PortfolioPosition)
            .scalar_subquery()
        )
        latest_change = (
            select(MarketQuote.change_amount)
            .where(MarketQuote.product_id == PortfolioPosition.product_id)
            .order_by(MarketQuote.market_timestamp.desc(), MarketQuote.id.desc())
            .limit(1)
            .correlate(PortfolioPosition)
            .scalar_subquery()
        )
        latest_change_percent = (
            select(MarketQuote.change_percent)
            .where(MarketQuote.product_id == PortfolioPosition.product_id)
            .order_by(MarketQuote.market_timestamp.desc(), MarketQuote.id.desc())
            .limit(1)
            .correlate(PortfolioPosition)
            .scalar_subquery()
        )
        latest_timestamp = (
            select(MarketQuote.market_timestamp)
            .where(MarketQuote.product_id == PortfolioPosition.product_id)
            .order_by(MarketQuote.market_timestamp.desc(), MarketQuote.id.desc())
            .limit(1)
            .correlate(PortfolioPosition)
            .scalar_subquery()
        )
        latest_source = (
            select(MarketQuote.source)
            .where(MarketQuote.product_id == PortfolioPosition.product_id)
            .order_by(MarketQuote.market_timestamp.desc(), MarketQuote.id.desc())
            .limit(1)
            .correlate(PortfolioPosition)
            .scalar_subquery()
        )
        statement = (
            select(
                InvestmentProduct.symbol,
                InvestmentProduct.product_type,
                InvestmentProduct.market,
                InvestmentProduct.currency_code,
                PortfolioPosition.quantity,
                PortfolioPosition.average_buy_price,
                PortfolioPosition.current_price.label("cached_price"),
                PortfolioPosition.updated_at.label("cached_price_updated_at"),
                latest_price.label("quote_price"),
                latest_change.label("quote_change_amount"),
                latest_change_percent.label("quote_change_percent"),
                latest_timestamp.label("quote_timestamp"),
                latest_source.label("quote_source"),
            )
            .join(
                InvestmentAccount,
                InvestmentAccount.id == PortfolioPosition.investment_account_id,
            )
            .join(
                InvestmentProduct,
                InvestmentProduct.id == PortfolioPosition.product_id,
            )
            .where(
                InvestmentAccount.user_id == user_id,
                InvestmentAccount.status == ACTIVE_STATUS,
                InvestmentProduct.status == ACTIVE_STATUS,
                PortfolioPosition.quantity > ZERO,
            )
            .order_by(InvestmentProduct.symbol)
        )
        return [
            HoldingRecord(
                symbol=row.symbol,
                product_type=row.product_type,
                market=row.market,
                currency_code=(
                    row.currency_code.upper() if row.currency_code else None
                ),
                quantity=row.quantity,
                average_buy_price=row.average_buy_price,
                cached_price=row.cached_price,
                cached_price_updated_at=row.cached_price_updated_at,
                quote_price=row.quote_price,
                quote_change_amount=row.quote_change_amount,
                quote_change_percent=row.quote_change_percent,
                quote_timestamp=row.quote_timestamp,
                quote_source=row.quote_source,
            )
            for row in self.db.execute(statement)
        ]

    def get_trades(self, user_id: UUID) -> list[TradeRecord]:
        statement = (
            select(
                InvestmentTrade.trade_number,
                InvestmentOrder.order_number,
                InvestmentProduct.symbol,
                InvestmentProduct.currency_code,
                InvestmentTrade.side,
                InvestmentTrade.quantity,
                InvestmentTrade.price,
                InvestmentTrade.commission,
                InvestmentTrade.tax,
                InvestmentTrade.total_amount,
                InvestmentTrade.executed_at,
            )
            .join(
                InvestmentAccount,
                InvestmentAccount.id == InvestmentTrade.investment_account_id,
            )
            .join(
                InvestmentProduct,
                InvestmentProduct.id == InvestmentTrade.product_id,
            )
            .join(InvestmentOrder, InvestmentOrder.id == InvestmentTrade.order_id)
            .where(
                InvestmentAccount.user_id == user_id,
                InvestmentAccount.status == ACTIVE_STATUS,
                InvestmentProduct.status == ACTIVE_STATUS,
                InvestmentOrder.user_id == user_id,
            )
            .order_by(InvestmentTrade.executed_at.desc(), InvestmentTrade.id.desc())
        )
        return [
            TradeRecord(
                trade_number=row.trade_number,
                order_number=row.order_number,
                symbol=row.symbol,
                currency_code=(
                    row.currency_code.upper() if row.currency_code else None
                ),
                side=row.side,
                quantity=row.quantity,
                price=row.price,
                commission=row.commission,
                tax=row.tax,
                total_amount=row.total_amount,
                executed_at=row.executed_at,
            )
            for row in self.db.execute(statement)
        ]

    def get_orders(self, user_id: UUID) -> list[OrderRecord]:
        statement = (
            select(
                InvestmentOrder.order_number,
                InvestmentProduct.symbol,
                InvestmentProduct.currency_code,
                InvestmentOrder.side,
                InvestmentOrder.quantity,
                InvestmentOrder.executed_quantity,
                InvestmentOrder.limit_price,
                InvestmentOrder.stop_price,
                InvestmentOrder.average_execution_price,
                InvestmentOrder.status,
                InvestmentOrder.submitted_at,
            )
            .join(
                InvestmentAccount,
                InvestmentAccount.id == InvestmentOrder.investment_account_id,
            )
            .join(
                InvestmentProduct,
                InvestmentProduct.id == InvestmentOrder.product_id,
            )
            .where(
                InvestmentOrder.user_id == user_id,
                InvestmentAccount.user_id == user_id,
                InvestmentAccount.status == ACTIVE_STATUS,
                InvestmentProduct.status == ACTIVE_STATUS,
            )
            .order_by(InvestmentOrder.submitted_at.desc(), InvestmentOrder.id.desc())
        )
        return [
            OrderRecord(
                order_number=row.order_number,
                symbol=row.symbol,
                currency_code=(
                    row.currency_code.upper() if row.currency_code else None
                ),
                side=row.side,
                quantity=row.quantity,
                executed_quantity=row.executed_quantity,
                limit_price=row.limit_price,
                stop_price=row.stop_price,
                average_execution_price=row.average_execution_price,
                status=row.status.lower() if row.status else None,
                submitted_at=row.submitted_at,
            )
            for row in self.db.execute(statement)
        ]


class InvestmentService:
    """Reusable investment use cases with user isolation and validated outputs."""

    def __init__(
        self,
        db: Session,
        repository: InvestmentRepository | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or SQLAlchemyInvestmentRepository(db)

    @contextmanager
    def _database_errors(self, message: str) -> Iterator[None]:
        try:
            yield
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise InvestmentDatabaseError(message) from exc

    def _normalize_and_validate_user(self, user_id: UserId) -> UUID:
        try:
            normalized = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise InvestmentUserNotFound(f"User {user_id!s} was not found") from exc
        if not self.repository.user_exists(normalized):
            raise InvestmentUserNotFound(f"User {normalized!s} was not found")
        return normalized

    def resolve_authenticated_user_id(self, national_id: str) -> UUID:
        normalized_national_id = national_id.strip()
        if not normalized_national_id:
            raise InvestmentUserNotFound("Authenticated user was not found")
        with self._database_errors("Could not resolve authenticated user"):
            user_id = self.repository.resolve_active_user_id(normalized_national_id)
        if user_id is None:
            raise InvestmentUserNotFound("Authenticated user was not found")
        return user_id

    def _price_state(self, holding: HoldingRecord) -> PriceState:
        if holding.quote_price is not None:
            return PriceState(
                price=holding.quote_price,
                as_of=holding.quote_timestamp,
                source=holding.quote_source,
                uses_quote=True,
            )

        if holding.cached_price is not None:
            return PriceState(
                price=holding.cached_price,
                as_of=holding.cached_price_updated_at,
                source="portfolio_positions.current_price",
                uses_quote=False,
            )

        return PriceState(
            price=None,
            as_of=holding.quote_timestamp or holding.cached_price_updated_at,
            source=None,
            uses_quote=False,
        )

    def _portfolio_records(
        self, user_id: UserId
    ) -> tuple[list[AccountRecord], list[HoldingRecord]]:
        normalized = self._normalize_and_validate_user(user_id)
        return (
            self.repository.get_accounts(normalized),
            self.repository.get_holdings(normalized),
        )

    def get_positions(self, user_id: UserId) -> list[Position]:
        with self._database_errors("Could not load investment positions"):
            normalized = self._normalize_and_validate_user(user_id)
            holdings = self.repository.get_holdings(normalized)

        positions: list[Position] = []
        for holding in holdings:
            _validate_holding(holding)
            price_state = self._price_state(holding)
            price = price_state.price
            cost_basis = holding.quantity * holding.average_buy_price
            total_value = holding.quantity * price if price is not None else None
            total_return = total_value - cost_basis if total_value is not None else None
            total_return_percent = (
                total_return / cost_basis * Decimal(100)
                if total_return is not None and cost_basis != ZERO
                else None
            )
            daily_return = (
                holding.quantity * holding.quote_change_amount
                if price_state.uses_quote and holding.quote_change_amount is not None
                else None
            )
            positions.append(
                Position(
                    symbol=holding.symbol,
                    currencyCode=_require_currency(holding.currency_code),
                    price=_as_float(price),
                    quantity=float(holding.quantity),
                    avgCost=float(holding.average_buy_price),
                    totalValue=_as_float(total_value),
                    dailyReturn=_as_float(daily_return),
                    dailyReturnPercent=(
                        _as_float(holding.quote_change_percent)
                        if price_state.uses_quote
                        else None
                    ),
                    totalReturn=_as_float(total_return),
                    totalReturnPercent=_as_float(total_return_percent),
                    priceAsOf=price_state.as_of,
                    priceSource=price_state.source,
                )
            )
        return positions

    def get_portfolio_summary(self, user_id: UserId) -> InvestmentBalance:
        """Return native TRY and USD totals without inventing an FX conversion.

        ``totalTRY`` contains TRY-denominated cash and holdings; ``totalUSD``
        contains USD-denominated cash and holdings. ``stocksUSUSD`` is therefore
        a native USD amount. A future FX provider can convert these into a single
        reporting currency without changing the database layer.
        """

        with self._database_errors("Could not load portfolio summary"):
            accounts, holdings = self._portfolio_records(user_id)

        totals = {"TRY": ZERO, "USD": ZERO}
        cash_try = ZERO
        stocks_bist = ZERO
        cash_usd = ZERO
        stocks_us_usd = ZERO

        for account in accounts:
            cash_balance = _require_non_negative_amount(
                account.cash_balance, "cash balance"
            )
            currency_code = _require_currency(account.currency_code)
            totals[currency_code] += cash_balance
            if currency_code == "TRY":
                cash_try += cash_balance
            elif currency_code == "USD":
                cash_usd += cash_balance

        for holding in holdings:
            _validate_holding(holding)
            price = _require_price(self._price_state(holding), holding.symbol)
            amount = holding.quantity * price
            currency_code = _require_currency(holding.currency_code)
            totals[currency_code] += amount
            market = (holding.market or "").upper()
            if holding.product_type.lower() == "stock" and market == "BIST":
                stocks_bist += amount
            elif holding.product_type.lower() == "stock" and market in _US_MARKETS:
                if currency_code != "USD":
                    raise InvestmentDataUnavailable(
                        f"US stock {holding.symbol} is not denominated in USD"
                    )
                stocks_us_usd += amount

        return InvestmentBalance(
            totalTRY=float(totals["TRY"]),
            totalUSD=float(totals["USD"]),
            breakdown=InvestmentBreakdown(
                cashTRY=float(cash_try),
                stocksBIST=float(stocks_bist),
                cashUSD=float(cash_usd),
                stocksUSUSD=float(stocks_us_usd),
            ),
        )

    def get_allocation(self, user_id: UserId) -> list[AssetAllocationItem]:
        """Calculate allocation when all non-zero values share one currency."""

        with self._database_errors("Could not load portfolio allocation"):
            accounts, holdings = self._portfolio_records(user_id)

        amounts: dict[str, Decimal] = {}
        currencies: set[str] = set()
        cash = ZERO
        for account in accounts:
            cash_balance = _require_non_negative_amount(
                account.cash_balance, "cash balance"
            )
            if cash_balance != ZERO:
                currencies.add(_require_currency(account.currency_code))
                cash += cash_balance
        if cash != ZERO:
            amounts["cash"] = cash

        for holding in holdings:
            _validate_holding(holding)
            amount = holding.quantity * _require_price(
                self._price_state(holding), holding.symbol
            )
            if amount == ZERO:
                continue
            currencies.add(_require_currency(holding.currency_code))
            asset_class = holding.product_type.lower()
            amounts[asset_class] = amounts.get(asset_class, ZERO) + amount

        if len(currencies) > 1:
            raise InvestmentDataUnavailable(
                "Allocation across multiple currencies requires an FX source"
            )

        total = sum(amounts.values(), ZERO)
        if total == ZERO:
            return []

        currency_code = next(iter(currencies), "TRY")
        sorted_amounts = sorted(amounts.items())
        percentages = [
            (amount / total * HUNDRED).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            for _, amount in sorted_amounts
        ]
        rounding_difference = HUNDRED - sum(percentages, ZERO)
        if percentages:
            largest_index = max(
                range(len(sorted_amounts)),
                key=lambda index: sorted_amounts[index][1],
            )
            percentages[largest_index] += rounding_difference

        return [
            AssetAllocationItem(
                assetClass=_ASSET_CLASS_NAMES.get(key, key.replace("_", " ").title()),
                percentage=float(percentages[index]),
                amount=float(amount),
                currencyCode=currency_code,
                color=_ASSET_CLASS_COLORS.get(key, "#64748b"),
            )
            for index, (key, amount) in enumerate(sorted_amounts)
        ]

    def get_orders(self, user_id: UserId) -> list[Order]:
        with self._database_errors("Could not load investment orders"):
            normalized = self._normalize_and_validate_user(user_id)
            records = self.repository.get_orders(normalized)

        status_map = {
            "pending": "Bekliyor",
            "partial": "Kısmi",
            "executed": "Gerçekleşti",
            "cancelled": "İptal",
        }
        orders: list[Order] = []
        for record in records:
            _validate_positive(record.quantity, "order quantity")
            side = _require_side(record.side)
            if record.status not in status_map:
                raise InvestmentDataUnavailable(
                    f"Unsupported order status {record.status!r}"
                )
            executed_quantity = record.executed_quantity
            if executed_quantity is not None:
                _validate_non_negative(executed_quantity, "executed order quantity")
                if executed_quantity > record.quantity:
                    raise InvestmentDataUnavailable(
                        f"Executed quantity exceeds order {record.order_number}"
                    )
            is_execution = record.status in {"partial", "executed"}
            price = (
                record.average_execution_price
                if is_execution
                else record.limit_price or record.stop_price
            )
            if price is not None:
                _validate_positive(price, "order price")
            total_quantity = executed_quantity if is_execution else record.quantity
            orders.append(
                Order(
                    id=record.order_number,
                    symbol=record.symbol,
                    status=status_map[record.status],
                    type="Alış" if side == "BUY" else "Satış",
                    currencyCode=_require_currency(record.currency_code),
                    quantity=float(record.quantity),
                    executedQuantity=_as_float(executed_quantity),
                    price=_as_float(price),
                    total=_as_float(
                        total_quantity * price
                        if total_quantity is not None and price is not None
                        else None
                    ),
                    date=record.submitted_at,
                )
            )
        return orders

    def get_transactions(self, user_id: UserId) -> list[InvestmentTransaction]:
        """Return executed fills separately from order lifecycle records."""

        with self._database_errors("Could not load investment transactions"):
            normalized = self._normalize_and_validate_user(user_id)
            trades = self.repository.get_trades(normalized)

        transactions: list[InvestmentTransaction] = []
        for trade in trades:
            side = _require_side(trade.side)
            _validate_positive(trade.quantity, "trade quantity")
            _validate_positive(trade.price, "trade price")
            commission = _require_non_negative_amount(
                trade.commission, "trade commission"
            )
            tax = _require_non_negative_amount(trade.tax, "trade tax")
            gross_amount = trade.quantity * trade.price
            expected_total = gross_amount + commission + tax
            if trade.total_amount != expected_total:
                raise InvestmentDataUnavailable(
                    f"Inconsistent total for trade {trade.trade_number}"
                )
            transactions.append(
                InvestmentTransaction(
                    id=trade.trade_number,
                    orderId=trade.order_number,
                    symbol=trade.symbol,
                    type="Alış" if side == "BUY" else "Satış",
                    currencyCode=_require_currency(trade.currency_code),
                    quantity=float(trade.quantity),
                    price=float(trade.price),
                    grossAmount=float(gross_amount),
                    commission=float(commission),
                    tax=float(tax),
                    total=float(trade.total_amount),
                    executedAt=trade.executed_at,
                )
            )
        return transactions


def get_positions(
    user_id: UserId,
    db: Session,
    *,
    repository: InvestmentRepository | None = None,
) -> list[Position]:
    return InvestmentService(db, repository).get_positions(user_id)


def get_portfolio_summary(
    user_id: UserId,
    db: Session,
    *,
    repository: InvestmentRepository | None = None,
) -> InvestmentBalance:
    return InvestmentService(db, repository).get_portfolio_summary(user_id)


def get_allocation(
    user_id: UserId,
    db: Session,
    *,
    repository: InvestmentRepository | None = None,
) -> list[AssetAllocationItem]:
    return InvestmentService(db, repository).get_allocation(user_id)


def get_orders(
    user_id: UserId,
    db: Session,
    *,
    repository: InvestmentRepository | None = None,
) -> list[Order]:
    return InvestmentService(db, repository).get_orders(user_id)


def get_transactions(
    user_id: UserId,
    db: Session,
    *,
    repository: InvestmentRepository | None = None,
) -> list[InvestmentTransaction]:
    return InvestmentService(db, repository).get_transactions(user_id)


def _as_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _require_price(price_state: PriceState, symbol: str) -> Decimal:
    if price_state.price is None:
        raise InvestmentDataUnavailable(f"No current price is available for {symbol}")
    return price_state.price


def _require_currency(currency: str | None) -> str:
    if currency is None:
        raise InvestmentDataUnavailable("Currency is missing")
    normalized = currency.upper()
    if normalized not in {"TRY", "USD"}:
        raise InvestmentDataUnavailable(f"Unsupported currency {currency!r}")
    return normalized


def _require_side(side: str) -> str:
    normalized = side.upper()
    if normalized not in {"BUY", "SELL"}:
        raise InvestmentDataUnavailable(f"Unsupported investment side {side!r}")
    return normalized


def _validate_holding(holding: HoldingRecord) -> None:
    _validate_positive(holding.quantity, "position quantity")
    _validate_non_negative(holding.average_buy_price, "average buy price")
    for value, field_name in (
        (holding.cached_price, "cached price"),
        (holding.quote_price, "market quote"),
    ):
        if value is not None:
            _validate_positive(value, field_name)


def _validate_positive(value: Decimal, field_name: str) -> None:
    if value <= ZERO:
        raise InvestmentDataUnavailable(f"{field_name} must be positive")


def _validate_non_negative(value: Decimal, field_name: str) -> None:
    if value < ZERO:
        raise InvestmentDataUnavailable(f"{field_name} must not be negative")


def _require_non_negative_amount(value: Decimal | None, field_name: str) -> Decimal:
    if value is None:
        raise InvestmentDataUnavailable(f"{field_name} is missing")
    _validate_non_negative(value, field_name)
    return value
