"""seed the Nasdaq-100 so the US market is tradable

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-21

The universe was 88 BIST names plus exactly three US tickers -- AAPL, MSFT and
NVDA -- which existed only because the demo portfolio holds them. Anything
American outside those three could not be screened, priced, charted or
traded, and a "US market" the user could switch to did not exist.

The membership list is hardcoded here rather than fetched, for the same reason
the BIST list in 0006 is: an index constituent list is a licensed product, and
a seed that silently changes under you is worse than one you can read in the
diff.

Every symbol below was resolved against the provider before this migration was
written; ANSS and EA were in the candidate list, returned no price data, and
were dropped rather than seeded as names nothing can quote. Company names come
from the provider too -- the daily fundamentals job would eventually backfill
them, but until it ran the whole US market would render as bare tickers.

US symbols carry no suffix, unlike BIST's `.IS`, so `data_symbol` equals
`symbol`.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Nasdaq-100 constituents, verified against the provider on 2026-08-21.
NASDAQ_100 = [
    ("AAPL", "Apple Inc."),
    ("ABNB", "Airbnb, Inc."),
    ("ADBE", "Adobe Inc."),
    ("ADI", "Analog Devices, Inc."),
    ("ADP", "Automatic Data Processing, Inc."),
    ("ADSK", "Autodesk, Inc."),
    ("AEP", "American Electric Power Company, Inc."),
    ("ALAB", "Astera Labs, Inc."),
    ("AMAT", "Applied Materials, Inc."),
    ("AMD", "Advanced Micro Devices, Inc."),
    ("AMGN", "Amgen Inc."),
    ("AMZN", "Amazon.com, Inc."),
    ("APP", "AppLovin Corporation"),
    ("ARM", "Arm Holdings plc"),
    ("AVGO", "Broadcom Inc."),
    ("AXON", "Axon Enterprise, Inc."),
    ("BIIB", "Biogen Inc."),
    ("BKNG", "Booking Holdings Inc."),
    ("BKR", "Baker Hughes Company"),
    ("CCEP", "Coca-Cola Europacific Partners PLC"),
    ("CDNS", "Cadence Design Systems, Inc."),
    ("CDW", "CDW Corporation"),
    ("CEG", "Constellation Energy Corporation"),
    ("CHTR", "Charter Communications, Inc."),
    ("CMCSA", "Comcast Corporation"),
    ("COST", "Costco Wholesale Corporation"),
    ("CPRT", "Copart, Inc."),
    ("CRWD", "CrowdStrike Holdings, Inc."),
    ("CSCO", "Cisco Systems, Inc."),
    ("CSGP", "CoStar Group, Inc."),
    ("CTAS", "Cintas Corporation"),
    ("CTSH", "Cognizant Technology Solutions Corporation"),
    ("DASH", "DoorDash, Inc."),
    ("DDOG", "Datadog, Inc."),
    ("DXCM", "DexCom, Inc."),
    ("EXC", "Exelon Corporation"),
    ("FANG", "Diamondback Energy, Inc."),
    ("FAST", "Fastenal Company"),
    ("FTNT", "Fortinet, Inc."),
    ("GEHC", "GE HealthCare Technologies Inc."),
    ("GFS", "GLOBALFOUNDRIES Inc."),
    ("GILD", "Gilead Sciences, Inc."),
    ("GOOG", "Alphabet Inc."),
    ("GOOGL", "Alphabet Inc."),
    ("HON", "Honeywell International Inc."),
    ("IDXX", "IDEXX Laboratories, Inc."),
    ("ILMN", "Illumina, Inc."),
    ("INTU", "Intuit Inc."),
    ("ISRG", "Intuitive Surgical, Inc."),
    ("KDP", "Keurig Dr Pepper Inc."),
    ("KHC", "The Kraft Heinz Company"),
    ("KLAC", "KLA Corporation"),
    ("LIN", "Linde plc"),
    ("LRCX", "Lam Research Corporation"),
    ("LULU", "lululemon athletica inc."),
    ("MAR", "Marriott International, Inc."),
    ("MCHP", "Microchip Technology Incorporated"),
    ("MDB", "MongoDB, Inc."),
    ("MDLZ", "Mondelez International, Inc."),
    ("MELI", "MercadoLibre, Inc."),
    ("META", "Meta Platforms, Inc."),
    ("MNST", "Monster Beverage Corporation"),
    ("MRVL", "Marvell Technology, Inc."),
    ("MSFT", "Microsoft Corporation"),
    ("MU", "Micron Technology, Inc."),
    ("NFLX", "Netflix, Inc."),
    ("NVDA", "NVIDIA Corporation"),
    ("NXPI", "NXP Semiconductors N.V."),
    ("ODFL", "Old Dominion Freight Line, Inc."),
    ("ON", "ON Semiconductor Corporation"),
    ("ORLY", "O'Reilly Automotive, Inc."),
    ("PANW", "Palo Alto Networks, Inc."),
    ("PAYX", "Paychex, Inc."),
    ("PCAR", "PACCAR Inc"),
    ("PDD", "PDD Holdings Inc."),
    ("PEP", "PepsiCo, Inc."),
    ("PYPL", "PayPal Holdings, Inc."),
    ("QCOM", "QUALCOMM Incorporated"),
    ("REGN", "Regeneron Pharmaceuticals, Inc."),
    ("ROP", "Roper Technologies, Inc."),
    ("ROST", "Ross Stores, Inc."),
    ("SBUX", "Starbucks Corporation"),
    ("SMCI", "Super Micro Computer, Inc."),
    ("SNPS", "Synopsys, Inc."),
    ("TEAM", "Atlassian Corporation"),
    ("TMUS", "T-Mobile US, Inc."),
    ("TSLA", "Tesla, Inc."),
    ("TTD", "The Trade Desk, Inc."),
    ("TTWO", "Take-Two Interactive Software, Inc."),
    ("TXN", "Texas Instruments Incorporated"),
    ("VRSK", "Verisk Analytics, Inc."),
    ("VRTX", "Vertex Pharmaceuticals Incorporated"),
    ("WBD", "Warner Bros. Discovery, Inc."),
    ("WDAY", "Workday, Inc."),
    ("XEL", "Xcel Energy Inc."),
    ("ZS", "Zscaler, Inc."),
]


def upgrade() -> None:
    connection = op.get_bind()
    for symbol, name in NASDAQ_100:
        connection.execute(
            sa.text(
                """
                INSERT INTO investment.investment_products
                    (id, symbol, data_symbol, name, product_type, market,
                     currency_code, status, created_at, updated_at)
                VALUES (gen_random_uuid()::text, :symbol, :symbol, :name,
                        'stock', 'NASDAQ', 'USD', 'active', now(), now())
                ON CONFLICT (symbol) DO UPDATE
                   SET data_symbol = EXCLUDED.data_symbol,
                       name = EXCLUDED.name,
                       market = EXCLUDED.market,
                       currency_code = EXCLUDED.currency_code,
                       updated_at = now()
                """
            ),
            {"symbol": symbol, "name": name},
        )


def downgrade() -> None:
    # AAPL, MSFT and NVDA predate this migration and are held by the demo
    # portfolio; removing them would orphan real positions.
    keep = ("AAPL", "MSFT", "NVDA")
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM investment.investment_products
             WHERE market = 'NASDAQ' AND symbol NOT IN :keep
            """
        ).bindparams(sa.bindparam("keep", expanding=True)),
        {"keep": list(keep)},
    )
