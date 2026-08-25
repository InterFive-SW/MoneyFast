"""seed investment products (the symbol map)

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-20

The join between the dummy portfolio and live market data.

Holdings keep the `TEST-` prefix so CLAUDE.md's "obviously fake customer data"
rule stays visible at a glance — a reviewer can tell a fabricated holding from
a real one by looking at it. `data_symbol` carries the ticker the provider
actually knows, so the prices themselves are real.

Index and FX rows have no `TEST-` prefix: they are not holdings and nothing
about them is fake.

Seeded as a migration rather than a startup script so the mapping is
versioned with the schema that depends on it, and so a fresh clone gets a
working dashboard without a separate manual step. ON CONFLICT DO NOTHING keeps
it re-runnable.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (symbol, data_symbol, name, product_type, market, currency)
PRODUCTS = [
    # Dummy holdings -> real BIST tickers.
    ("TEST-THYAO", "THYAO.IS", "Türk Hava Yolları A.O.", "stock", "BIST", "TRY"),
    ("TEST-SISE", "SISE.IS", "Türkiye Şişe ve Cam Fabrikaları A.Ş.", "stock", "BIST", "TRY"),
    ("TEST-TUPRS", "TUPRS.IS", "Tüpraş", "stock", "BIST", "TRY"),
    ("TEST-KCHOL", "KCHOL.IS", "Koç Holding A.Ş.", "stock", "BIST", "TRY"),
    ("TEST-FROTO", "FROTO.IS", "Ford Otosan", "stock", "BIST", "TRY"),
    ("TEST-EREGL", "EREGL.IS", "Ereğli Demir ve Çelik", "stock", "BIST", "TRY"),
    # Dummy holdings -> real US tickers.
    ("TEST-AAPL", "AAPL", "Apple Inc.", "stock", "NASDAQ", "USD"),
    ("TEST-MSFT", "MSFT", "Microsoft Corporation", "stock", "NASDAQ", "USD"),
    ("TEST-NVDA", "NVDA", "NVIDIA Corporation", "stock", "NASDAQ", "USD"),
    # Index and FX for the dashboard strip. USDTRY doubles as the conversion
    # rate for USD-quoted holdings, which is why it is a product row rather
    # than a constant somewhere: one source, one number.
    ("XU100", "XU100.IS", "BIST 100 Endeksi", "index", "BIST", "TRY"),
    ("USDTRY", "USDTRY=X", "ABD Doları / Türk Lirası", "fx", "FX", "TRY"),
    ("EURTRY", "EURTRY=X", "Euro / Türk Lirası", "fx", "FX", "TRY"),
    ("XAUUSD", "GC=F", "Altın (Ons/USD)", "commodity", "COMEX", "USD"),
]


def upgrade() -> None:
    connection = op.get_bind()
    for symbol, data_symbol, name, product_type, market, currency in PRODUCTS:
        connection.execute(
            sa.text(
                """
                INSERT INTO investment.investment_products
                    (id, symbol, data_symbol, name, product_type, market,
                     currency_code, status, created_at, updated_at)
                VALUES
                    (gen_random_uuid()::text, :symbol, :data_symbol, :name,
                     :product_type, :market, :currency, 'active', now(), now())
                ON CONFLICT (symbol) DO UPDATE
                    SET data_symbol = EXCLUDED.data_symbol,
                        name = EXCLUDED.name,
                        updated_at = now()
                """
            ),
            {
                "symbol": symbol,
                "data_symbol": data_symbol,
                "name": name,
                "product_type": product_type,
                "market": market,
                "currency": currency,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM investment.investment_products WHERE symbol = ANY(:symbols)"),
        {"symbols": [row[0] for row in PRODUCTS]},
    )
