"""real ticker symbols, BIST 100 universe, fundamentals, and seeded holdings

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-20

Four changes in one migration, because CLAUDE.md calls migrations the single
real conflict point between team members and four separate ones is four
coordination moments instead of one.

1. **The `TEST-` prefix is gone.** It was meant to keep fake customer data
   visible at a glance, but it also meant the assistant rejected "THYAO"
   because it only knew "TEST-THYAO" — a chatbot nobody could use. What is
   actually synthetic is the *account* (quantity, cost basis), not the
   instrument, so the marker moves to where the fiction lives.

2. **The universe grows to BIST 100 plus US/FX.** Three names Yahoo no longer
   quotes (IPEKE, KOZAL, KOZAA) are seeded with `data_symbol = NULL`, which
   `list_products()` already reads as "do not price this".

3. **`market_quotes` becomes one row per product.** At six cycles a minute
   append-only adds ~112k rows a day for a tick history nothing reads. The
   existing rows are discarded: they are all stale within ten seconds anyway,
   and every one is re-derivable from the next cycle.

4. **Holdings get a real home** in `investment_accounts` +
   `portfolio_positions`, per the design in `infra/intertech.sql:327`.
   Quantities are seeded here; `average_buy_price` is left at 0 and backfilled
   from real historical closes by `scripts/seed_portfolio.py`, because the
   candles it needs are ingested rather than shipped.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: BIST constituents, verified against the provider on 2026-08-20.
BIST = """AKBNK ARCLK ASELS ASTOR BIMAS BRSAN CIMSA DOAS EKGYO ENKAI EREGL FROTO
GARAN GUBRF HEKTS ISCTR KCHOL KONTR KRDMD MGROS ODAS OYAKC PETKM PGSUS SAHOL
SASA SISE SOKM TAVHL TCELL THYAO TOASO TTKOM TUPRS ULKER VESTL YKBNK ZOREN
AEFES AGHOL AKSA AKSEN ALARK ALBRK ANSGR BAGFS BERA BIENY BOBET CANTE CCOLA
CWENE DOHOL ECILC EGEEN ENJSA EUPWR GESAN GLYHO GWIND HALKB ISMEN IZMDC KARSN
KLSER KMPUR KORDS LOGO MAVI MIATK NTHOL OTKAR PENTA PSGYO QUAGR SKBNK SMRTG
SNGYO TKFEN TMSN TSKB TTRAK TURSG VAKBN VESBE YATAS YEOTK""".split()

#: Quoted by BIST but not by our provider. Seeded so a screen shows the whole
#: universe, with data_symbol NULL so nothing tries to price them.
UNQUOTED = ["IPEKE", "KOZAL", "KOZAA"]

US = [("AAPL", "AAPL", "Apple Inc.", "NASDAQ", "USD"),
      ("MSFT", "MSFT", "Microsoft Corporation", "NASDAQ", "USD"),
      ("NVDA", "NVDA", "NVIDIA Corporation", "NASDAQ", "USD")]

BENCHMARKS = [("XU100", "XU100.IS", "BIST 100 Endeksi", "index", "BIST", "TRY"),
              ("USDTRY", "USDTRY=X", "ABD Doları / Türk Lirası", "fx", "FX", "TRY"),
              ("EURTRY", "EURTRY=X", "Euro / Türk Lirası", "fx", "FX", "TRY"),
              ("XAUUSD", "GC=F", "Altın (Ons/USD)", "commodity", "COMEX", "USD")]

#: The demo portfolio. Quantities only — the cost basis is backfilled from real
#: historical closes once candles exist.
HOLDINGS = [("THYAO", 120), ("SISE", 500), ("TUPRS", 150), ("KCHOL", 80),
            ("FROTO", 25), ("EREGL", 1000), ("GARAN", 400), ("ASELS", 300),
            ("AAPL", 15), ("MSFT", 10), ("NVDA", 25)]

DEMO_ACCOUNT = "TR-DEMO-0001"


def upgrade() -> None:
    connection = op.get_bind()

    # ---- 1. drop the TEST- prefix ---------------------------------------
    # Renames rather than re-inserts, so anything already referencing a
    # product id (quotes, candles) follows the row instead of orphaning.
    connection.execute(
        sa.text(
            """
            UPDATE investment.investment_products
            SET symbol = regexp_replace(symbol, '^TEST-', ''), updated_at = now()
            WHERE symbol LIKE 'TEST-%'
            """
        )
    )

    # ---- 2. widen the universe ------------------------------------------
    rows = [(s, f"{s}.IS", s, "stock", "BIST", "TRY") for s in BIST]
    rows += [(s, None, s, "stock", "BIST", "TRY") for s in UNQUOTED]
    rows += [(sym, data, name, "stock", market, ccy) for sym, data, name, market, ccy in US]
    rows += [(sym, data, name, kind, market, ccy) for sym, data, name, kind, market, ccy in BENCHMARKS]

    for symbol, data_symbol, name, kind, market, currency in rows:
        connection.execute(
            sa.text(
                """
                INSERT INTO investment.investment_products
                    (id, symbol, data_symbol, name, product_type, market,
                     currency_code, status, created_at, updated_at)
                VALUES (gen_random_uuid()::text, :symbol, :data_symbol, :name,
                        :kind, :market, :currency, 'active', now(), now())
                ON CONFLICT (symbol) DO UPDATE
                   SET data_symbol = EXCLUDED.data_symbol,
                       product_type = EXCLUDED.product_type,
                       market = EXCLUDED.market,
                       updated_at = now()
                """
            ),
            {"symbol": symbol, "data_symbol": data_symbol, "name": name,
             "kind": kind, "market": market, "currency": currency},
        )

    # ---- 3. one quote row per product -----------------------------------
    # Discarded rather than deduplicated: every existing row is stale within
    # ten seconds and is re-derived by the next cycle.
    op.execute("TRUNCATE investment.market_quotes")
    op.create_unique_constraint(
        "uq_market_quotes_product", "market_quotes", ["product_id"], schema="investment"
    )

    op.create_table(
        "instrument_fundamentals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        # Every ratio is nullable and stays that way. Provider coverage is
        # partial, and a missing P/E defaulted to zero would make a stock with
        # no earnings data look like the cheapest name on the screen.
        sa.Column("pe_ratio", sa.Numeric(19, 4), nullable=True),
        sa.Column("pb_ratio", sa.Numeric(19, 4), nullable=True),
        sa.Column("market_cap", sa.BigInteger(), nullable=True),
        sa.Column("dividend_yield", sa.Numeric(10, 4), nullable=True),
        sa.Column("sector", sa.String(length=80), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("week52_high", sa.Numeric(19, 4), nullable=True),
        sa.Column("week52_low", sa.Numeric(19, 4), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["investment.investment_products.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", name="uq_instrument_fundamentals_product"),
        schema="investment",
    )

    # ---- 4. accounts and holdings ---------------------------------------
    op.create_table(
        "investment_accounts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("account_number", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("cash_balance", sa.Numeric(19, 4), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_number"),
        schema="investment",
    )
    op.create_index("ix_investment_accounts_user", "investment_accounts", ["user_id"],
                    schema="investment")

    op.create_table(
        "portfolio_positions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("investment_account_id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("quantity", sa.Numeric(19, 6), nullable=False),
        sa.Column("average_buy_price", sa.Numeric(19, 4), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["investment_account_id"],
                                ["investment.investment_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["investment.investment_products.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("investment_account_id", "product_id",
                            name="uq_portfolio_positions_holding"),
        schema="investment",
    )

    # The demo account is not tied to a user row: it exists so a fresh clone
    # has something to show, and seed_portfolio.py claims it for whoever
    # registers first.
    connection.execute(
        sa.text(
            """
            INSERT INTO investment.investment_accounts
                (id, user_id, account_number, name, currency_code, cash_balance,
                 status, created_at)
            VALUES (gen_random_uuid()::text, 'demo', :number, 'Demo Yatırım Hesabı',
                    'TRY', 25000, 'active', now())
            ON CONFLICT (account_number) DO NOTHING
            """
        ),
        {"number": DEMO_ACCOUNT},
    )

    for symbol, quantity in HOLDINGS:
        connection.execute(
            sa.text(
                """
                INSERT INTO investment.portfolio_positions
                    (id, investment_account_id, product_id, quantity,
                     average_buy_price, opened_at, updated_at)
                SELECT gen_random_uuid()::text, a.id, p.id, :quantity, 0, now(), now()
                FROM investment.investment_accounts a,
                     investment.investment_products p
                WHERE a.account_number = :number AND p.symbol = :symbol
                ON CONFLICT (investment_account_id, product_id) DO NOTHING
                """
            ),
            {"quantity": quantity, "number": DEMO_ACCOUNT, "symbol": symbol},
        )


def downgrade() -> None:
    op.drop_table("portfolio_positions", schema="investment")
    op.drop_index("ix_investment_accounts_user", table_name="investment_accounts",
                  schema="investment")
    op.drop_table("investment_accounts", schema="investment")
    op.drop_table("instrument_fundamentals", schema="investment")
    op.drop_constraint("uq_market_quotes_product", "market_quotes", schema="investment")
    op.execute(
        """
        UPDATE investment.investment_products
        SET symbol = 'TEST-' || symbol
        WHERE symbol IN ('THYAO','SISE','TUPRS','KCHOL','FROTO','EREGL','AAPL','MSFT','NVDA')
        """
    )
