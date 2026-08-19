import os
from unittest import TestCase, main
from unittest.mock import MagicMock
from uuid import UUID

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "TEST-ONLY-NOT-A-SECRET")

from sqlalchemy.dialects import postgresql

from app.modules.investment.service import SQLAlchemyInvestmentRepository

USER_ID = UUID("123e4567-e89b-12d3-a456-426614174000")


class InvestmentRepositoryQueryTests(TestCase):
    def setUp(self) -> None:
        self.db = MagicMock()
        self.db.execute.return_value = []
        self.repository = SQLAlchemyInvestmentRepository(self.db)

    def compiled_query(self) -> str:
        statement = self.db.execute.call_args.args[0]
        return str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )

    def test_accounts_are_scoped_to_user_and_active_status(self) -> None:
        self.repository.get_accounts(USER_ID)

        query = self.compiled_query()
        self.assertIn("investment.investment_accounts.user_id =", query)
        self.assertIn("investment.investment_accounts.status = 'active'", query)

    def test_holdings_are_user_scoped_active_and_open(self) -> None:
        self.repository.get_holdings(USER_ID)

        query = self.compiled_query()
        self.assertIn("investment.investment_accounts.user_id =", query)
        self.assertIn("investment.investment_accounts.status = 'active'", query)
        self.assertIn("investment.investment_products.status = 'active'", query)
        self.assertIn("investment.portfolio_positions.quantity > 0", query)
        self.assertIn("market_timestamp", query)
        self.assertIn("source", query)

    def test_orders_require_matching_order_and_account_owner(self) -> None:
        self.repository.get_orders(USER_ID)

        query = self.compiled_query()
        self.assertIn("investment.investment_orders.user_id =", query)
        self.assertIn("investment.investment_accounts.user_id =", query)
        self.assertIn("investment.investment_accounts.status = 'active'", query)

    def test_trades_require_matching_order_and_account_owner(self) -> None:
        self.repository.get_trades(USER_ID)

        query = self.compiled_query()
        self.assertIn("investment.investment_orders.user_id =", query)
        self.assertIn("investment.investment_accounts.user_id =", query)
        self.assertIn("investment.investment_accounts.status = 'active'", query)
        self.assertIn("investment.investment_trades.order_id", query)

    def test_national_id_resolution_only_returns_active_user(self) -> None:
        self.db.scalar.return_value = USER_ID

        result = self.repository.resolve_active_user_id("TEST-10000000146")

        self.assertEqual(result, USER_ID)
        statement = self.db.scalar.call_args.args[0]
        query = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("auth.users.national_id = 'TEST-10000000146'", query)
        self.assertIn("auth.users.status = 'active'", query)


if __name__ == "__main__":
    main()
