"""SQLAlchemy mappings owned by the investment module.

The table and column names mirror ``infra/intertech.sql``.  Relationships are
intentionally omitted so callers cannot accidentally cross module boundaries;
queries join through foreign-key identifiers explicitly.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InvestmentProduct(Base):
    __tablename__ = "investment_products"
    __table_args__ = ({"schema": "investment"},)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_type: Mapped[str] = mapped_column(String(50), nullable=False)
    market: Mapped[str | None] = mapped_column(String(50))
    currency_code: Mapped[str | None] = mapped_column(
        String(3), server_default=text("'TRY'")
    )
    description: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(String(20))
    week52_low: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    week52_high: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    status: Mapped[str | None] = mapped_column(
        String(20), server_default=text("'active'")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class MarketQuote(Base):
    __tablename__ = "market_quotes"
    __table_args__ = ({"schema": "investment"},)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("investment.investment_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    change_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    change_percent: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    bid_price: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    ask_price: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    market_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)


class MarketCandle(Base):
    __tablename__ = "market_candles"
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "interval",
            "timestamp",
            name="market_candles_product_id_interval_timestamp_key",
        ),
        {"schema": "investment"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("investment.investment_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    high_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    low_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str | None] = mapped_column(String(50))


class InvestmentAccount(Base):
    __tablename__ = "investment_accounts"
    __table_args__ = ({"schema": "investment"},)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("banking.accounts.id", ondelete="RESTRICT")
    )
    account_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    currency_code: Mapped[str | None] = mapped_column(
        String(3), server_default=text("'TRY'")
    )
    cash_balance: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 4), server_default=text("0")
    )
    available_cash: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 4), server_default=text("0")
    )
    buying_power: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 4), server_default=text("0")
    )
    pending_settlement: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 4), server_default=text("0")
    )
    status: Mapped[str | None] = mapped_column(
        String(20), server_default=text("'active'")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"
    __table_args__ = (
        UniqueConstraint(
            "investment_account_id",
            "product_id",
            name="portfolio_positions_investment_account_id_product_id_key",
        ),
        {"schema": "investment"},
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    investment_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("investment.investment_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("investment.investment_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(19, 6), nullable=False, server_default=text("0")
    )
    average_buy_price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    market_value: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    unrealized_pnl_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    __table_args__ = ({"schema": "investment"},)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    investment_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("investment.investment_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    total_market_value: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, server_default=text("0")
    )
    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, server_default=text("0")
    )
    total_value: Mapped[Decimal] = mapped_column(
        Numeric(19, 4), nullable=False, server_default=text("0")
    )
    daily_pnl: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    daily_pnl_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    total_pnl: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    total_pnl_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))


class InvestmentOrder(Base):
    __tablename__ = "investment_orders"
    __table_args__ = ({"schema": "investment"},)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    investment_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("investment.investment_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("investment.investment_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(19, 6), nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    executed_quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 6), server_default=text("0")
    )
    remaining_quantity: Mapped[Decimal | None] = mapped_column(Numeric(19, 6))
    average_execution_price: Mapped[Decimal | None] = mapped_column(Numeric(19, 4))
    status: Mapped[str | None] = mapped_column(
        String(20), server_default=text("'pending'")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvestmentTrade(Base):
    __tablename__ = "investment_trades"
    __table_args__ = ({"schema": "investment"},)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    trade_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    order_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("investment.investment_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    investment_account_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("investment.investment_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("investment.investment_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(19, 6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    commission: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 4), server_default=text("0")
    )
    tax: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 4), server_default=text("0")
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


Index(
    "idx_market_quotes_product_time",
    MarketQuote.product_id,
    MarketQuote.market_timestamp.desc(),
)
Index(
    "idx_market_candles_product_interval_time",
    MarketCandle.product_id,
    MarketCandle.interval,
    MarketCandle.timestamp.desc(),
)
