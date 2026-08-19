import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import TestCase, main
from unittest.mock import MagicMock
from uuid import UUID

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "TEST-ONLY-NOT-A-SECRET")

from app.modules.investment.service import (
    AccountRecord,
    HoldingRecord,
    InvestmentDataUnavailable,
    InvestmentService,
    InvestmentUserNotFound,
    OrderRecord,
    TradeRecord,
)

USER_ID = UUID("123e4567-e89b-12d3-a456-426614174000")
NOW = datetime(2026, 8, 19, 9, 0, tzinfo=timezone.utc)


class FakeInvestmentRepository:
    def __init__(
        self,
        *,
        exists: bool = True,
        accounts: list[AccountRecord] | None = None,
        holdings: list[HoldingRecord] | None = None,
        trades: list[TradeRecord] | None = None,
        orders: list[OrderRecord] | None = None,
    ) -> None:
        self.exists = exists
        self.accounts = accounts or []
        self.holdings = holdings or []
        self.trades = trades or []
        self.orders = orders or []

    def user_exists(self, user_id: UUID) -> bool:
        return self.exists and user_id == USER_ID

    def resolve_active_user_id(self, national_id: str) -> UUID | None:
        return USER_ID if self.exists and national_id == "TEST-10000000146" else None

    def get_accounts(self, user_id: UUID) -> list[AccountRecord]:
        return self.accounts

    def get_holdings(self, user_id: UUID) -> list[HoldingRecord]:
        return self.holdings

    def get_trades(self, user_id: UUID) -> list[TradeRecord]:
        return self.trades

    def get_orders(self, user_id: UUID) -> list[OrderRecord]:
        return self.orders


def holding(
    *,
    symbol: str = "TEST-THYAO",
    product_type: str = "stock",
    market: str = "BIST",
    currency: str = "TRY",
    quantity: str = "10",
    average_cost: str = "90",
    cached_price: str | None = None,
    quote_price: str | None = "100",
    change_amount: str | None = "2",
    change_percent: str | None = "2.04",
    cached_at: datetime | None = None,
    quote_at: datetime | None = NOW,
) -> HoldingRecord:
    return HoldingRecord(
        symbol=symbol,
        product_type=product_type,
        market=market,
        currency_code=currency,
        quantity=Decimal(quantity),
        average_buy_price=Decimal(average_cost),
        cached_price=Decimal(cached_price) if cached_price is not None else None,
        cached_price_updated_at=cached_at,
        quote_price=Decimal(quote_price) if quote_price is not None else None,
        quote_change_amount=(
            Decimal(change_amount) if change_amount is not None else None
        ),
        quote_change_percent=(
            Decimal(change_percent) if change_percent is not None else None
        ),
        quote_timestamp=quote_at,
        quote_source="TEST-MARKET" if quote_at is not None else None,
    )


class InvestmentServiceTests(TestCase):
    def service(self, repository: FakeInvestmentRepository) -> InvestmentService:
        return InvestmentService(MagicMock(), repository)

    def test_get_positions_calculates_returns_from_database_values(self) -> None:
        positions = self.service(
            FakeInvestmentRepository(holdings=[holding()])
        ).get_positions(USER_ID)

        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].symbol, "TEST-THYAO")
        self.assertEqual(positions[0].totalValue, 1000.0)
        self.assertEqual(positions[0].dailyReturn, 20.0)
        self.assertEqual(positions[0].totalReturn, 100.0)
        self.assertAlmostEqual(
            positions[0].totalReturnPercent or 0, 11.111111, places=6
        )

    def test_get_positions_returns_empty_list_for_user_without_positions(self) -> None:
        positions = self.service(FakeInvestmentRepository()).get_positions(USER_ID)

        self.assertEqual(positions, [])

    def test_position_does_not_fabricate_missing_daily_change(self) -> None:
        positions = self.service(
            FakeInvestmentRepository(
                holdings=[
                    holding(
                        cached_price="100",
                        quote_price=None,
                        change_amount=None,
                        change_percent=None,
                        cached_at=NOW,
                        quote_at=None,
                    )
                ]
            )
        ).get_positions(USER_ID)

        self.assertEqual(positions[0].price, 100.0)
        self.assertIsNone(positions[0].dailyReturn)
        self.assertIsNone(positions[0].dailyReturnPercent)

    def test_portfolio_summary_keeps_try_and_usd_in_native_currencies(self) -> None:
        repository = FakeInvestmentRepository(
            accounts=[
                AccountRecord("TRY", Decimal(1000)),
                AccountRecord("USD", Decimal(50)),
            ],
            holdings=[
                holding(quantity="2", quote_price="100"),
                holding(
                    symbol="TEST-AAPL",
                    market="NASDAQ",
                    currency="USD",
                    quantity="1",
                    quote_price="150",
                ),
            ],
        )

        summary = self.service(repository).get_portfolio_summary(USER_ID)

        self.assertEqual(summary.totalTRY, 1200.0)
        self.assertEqual(summary.totalUSD, 200.0)
        self.assertEqual(summary.breakdown.cashTRY, 1000.0)
        self.assertEqual(summary.breakdown.stocksBIST, 200.0)
        self.assertEqual(summary.breakdown.cashUSD, 50.0)
        self.assertEqual(summary.breakdown.stocksUSUSD, 150.0)

    def test_allocation_percentages_use_actual_single_currency_values(self) -> None:
        repository = FakeInvestmentRepository(
            accounts=[AccountRecord("TRY", Decimal(100))],
            holdings=[
                holding(quantity="3", quote_price="100"),
                holding(
                    symbol="TEST-FUND",
                    product_type="fund",
                    market="BIST",
                    quantity="1",
                    quote_price="100",
                ),
            ],
        )

        allocation = self.service(repository).get_allocation(USER_ID)
        by_name = {item.assetClass: item for item in allocation}

        self.assertEqual(by_name["Nakit"].percentage, 20.0)
        self.assertEqual(by_name["Hisse Senedi"].percentage, 60.0)
        self.assertEqual(by_name["Yatırım Fonu"].percentage, 20.0)
        self.assertEqual(sum(item.percentage for item in allocation), 100.0)

    def test_allocation_rejects_mixed_currency_values_without_fx(self) -> None:
        repository = FakeInvestmentRepository(
            accounts=[AccountRecord("TRY", Decimal(100))],
            holdings=[
                holding(
                    symbol="TEST-AAPL",
                    market="NASDAQ",
                    currency="USD",
                    quantity="1",
                    quote_price="100",
                )
            ],
        )

        with self.assertRaises(InvestmentDataUnavailable):
            self.service(repository).get_allocation(USER_ID)

    def test_unknown_user_raises_domain_exception(self) -> None:
        service = self.service(FakeInvestmentRepository(exists=False))

        with self.assertRaises(InvestmentUserNotFound):
            service.get_positions(USER_ID)

    def test_empty_repository_results_are_deterministic(self) -> None:
        service = self.service(FakeInvestmentRepository())

        self.assertEqual(service.get_positions(USER_ID), [])
        self.assertEqual(service.get_allocation(USER_ID), [])
        self.assertEqual(service.get_orders(USER_ID), [])
        self.assertEqual(service.get_transactions(USER_ID), [])
        summary = service.get_portfolio_summary(USER_ID)
        self.assertEqual(summary.totalTRY, 0.0)
        self.assertEqual(summary.totalUSD, 0.0)

    def test_transactions_use_executed_trades_and_existing_order_schema(self) -> None:
        repository = FakeInvestmentRepository(
            trades=[
                TradeRecord(
                    trade_number="TEST-TRADE-1",
                    order_number="TEST-ORDER-1",
                    symbol="TEST-THYAO",
                    currency_code="TRY",
                    side="BUY",
                    quantity=Decimal(2),
                    price=Decimal(100),
                    commission=Decimal(1),
                    tax=Decimal(0),
                    total_amount=Decimal(201),
                    executed_at=datetime(2026, 8, 19, 9, 0, tzinfo=timezone.utc),
                )
            ]
        )

        transactions = self.service(repository).get_transactions(USER_ID)

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].id, "TEST-TRADE-1")
        self.assertEqual(transactions[0].orderId, "TEST-ORDER-1")
        self.assertEqual(transactions[0].type, "Alış")
        self.assertEqual(transactions[0].total, 201.0)

    def test_old_quote_keeps_timestamp_without_service_freshness_policy(self) -> None:
        old_quote = holding(quote_at=NOW - timedelta(days=2))
        service = self.service(FakeInvestmentRepository(holdings=[old_quote]))

        position = service.get_positions(USER_ID)[0]

        self.assertEqual(position.price, 100.0)
        self.assertEqual(position.priceAsOf, old_quote.quote_timestamp)
        self.assertEqual(position.priceSource, "TEST-MARKET")
        self.assertEqual(service.get_portfolio_summary(USER_ID).totalTRY, 1000.0)

    def test_cached_price_is_used_when_quote_is_missing(self) -> None:
        position = self.service(
            FakeInvestmentRepository(
                holdings=[
                    holding(
                        quote_price=None,
                        quote_at=None,
                        cached_price="101",
                        cached_at=NOW - timedelta(minutes=5),
                    )
                ]
            )
        ).get_positions(USER_ID)[0]

        self.assertEqual(position.price, 101.0)
        self.assertEqual(position.priceSource, "portfolio_positions.current_price")
        self.assertIsNone(position.dailyReturn)

    def test_orders_preserve_pending_cancelled_and_partial_lifecycle(self) -> None:
        records = [
            OrderRecord(
                order_number=f"TEST-ORDER-{status}",
                symbol="TEST-THYAO",
                currency_code="TRY",
                side="BUY",
                quantity=Decimal(2),
                executed_quantity=Decimal(1) if status == "partial" else Decimal(0),
                limit_price=Decimal(100),
                stop_price=None,
                average_execution_price=None,
                status=status,
                submitted_at=NOW,
            )
            for status in ("pending", "partial", "cancelled")
        ]

        orders = self.service(FakeInvestmentRepository(orders=records)).get_orders(
            USER_ID
        )

        self.assertEqual(
            [order.status for order in orders], ["Bekliyor", "Kısmi", "İptal"]
        )

    def test_inconsistent_trade_total_is_rejected(self) -> None:
        repository = FakeInvestmentRepository(
            trades=[
                TradeRecord(
                    trade_number="TEST-BAD-TRADE",
                    order_number="TEST-ORDER",
                    symbol="TEST-THYAO",
                    currency_code="TRY",
                    side="SELL",
                    quantity=Decimal(2),
                    price=Decimal(100),
                    commission=Decimal(1),
                    tax=Decimal(1),
                    total_amount=Decimal(200),
                    executed_at=NOW,
                )
            ]
        )

        with self.assertRaises(InvestmentDataUnavailable):
            self.service(repository).get_transactions(USER_ID)

    def test_negative_cash_and_quantity_are_rejected(self) -> None:
        with self.assertRaises(InvestmentDataUnavailable):
            self.service(
                FakeInvestmentRepository(accounts=[AccountRecord("TRY", Decimal(-1))])
            ).get_portfolio_summary(USER_ID)

        with self.assertRaises(InvestmentDataUnavailable):
            self.service(
                FakeInvestmentRepository(holdings=[holding(quantity="-1")])
            ).get_positions(USER_ID)

    def test_missing_cash_balance_is_not_replaced_with_zero(self) -> None:
        with self.assertRaises(InvestmentDataUnavailable):
            self.service(
                FakeInvestmentRepository(accounts=[AccountRecord("TRY", None)])
            ).get_portfolio_summary(USER_ID)

    def test_authenticated_national_id_resolves_to_uuid(self) -> None:
        service = self.service(FakeInvestmentRepository())

        self.assertEqual(
            service.resolve_authenticated_user_id("TEST-10000000146"), USER_ID
        )
        with self.assertRaises(InvestmentUserNotFound):
            service.resolve_authenticated_user_id("TEST-UNKNOWN")

    def test_allocation_rounding_sums_to_exactly_one_hundred(self) -> None:
        allocation = self.service(
            FakeInvestmentRepository(
                holdings=[
                    holding(symbol="TEST-A", quantity="1", quote_price="1"),
                    holding(
                        symbol="TEST-B",
                        product_type="fund",
                        quantity="1",
                        quote_price="1",
                    ),
                    holding(
                        symbol="TEST-C",
                        product_type="bond",
                        quantity="1",
                        quote_price="1",
                    ),
                ]
            )
        ).get_allocation(USER_ID)

        self.assertEqual(sum(item.percentage for item in allocation), 100.0)
        self.assertTrue(all(item.currencyCode == "TRY" for item in allocation))


if __name__ == "__main__":
    main()
