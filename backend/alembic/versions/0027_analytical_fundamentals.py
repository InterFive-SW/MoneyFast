"""Gelir tablosu ve kârlılık alanları.

`instrument_fundamentals` sekiz alan tutuyordu: F/K, PD/DD, piyasa değeri,
temettü verimi, sektör, sanayi ve 52 hafta aralığı. Bunlarla bir hissenin
NEYE değdiği söylenebiliyordu ama nasıl gittiği söylenemiyordu -- marjı
daralıyor mu, borcu ne, özkaynağını ne kadar verimli kullanıyor.

Yeni bir sağlayıcı ya da yeni bir istek yok: ingestor zaten
`yf.Ticker(sym).info` çağırıyor ve dönen ~150 alanın sekizini alıp gerisini
atıyordu. Ölçüldü: THYAO ve AAPL için bu alanların 27'sinin 27'si, AKBNK
için 23'ü geliyor (bankada brüt marj ve cari oran kavramı yok, o boşluklar
gerçek).

Hepsi nullable ve öyle kalıyor -- tablonun kendi kuralı: eksik bir oranı
sıfıra çevirmek, kazanç verisi olmayan bir hisseyi ekrandaki en ucuz isim
gibi gösterir.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-31 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0027'
down_revision: Union[str, None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "investment"
TABLE = "instrument_fundamentals"

#: (kolon, tip). Oranlar kesir olarak saklanıyor (0,1287 = %12,87), sağlayıcı
#: onları böyle veriyor ve yüzdeye çevirmek gösterim katmanının işi.
COLUMNS = (
    ("total_revenue", sa.BigInteger()),
    ("revenue_growth", sa.Numeric(10, 4)),
    ("gross_margin", sa.Numeric(10, 4)),
    ("operating_margin", sa.Numeric(10, 4)),
    ("ebitda_margin", sa.Numeric(10, 4)),
    ("profit_margin", sa.Numeric(10, 4)),
    ("return_on_equity", sa.Numeric(10, 4)),
    ("return_on_assets", sa.Numeric(10, 4)),
    ("debt_to_equity", sa.Numeric(19, 4)),
    ("current_ratio", sa.Numeric(10, 4)),
    ("total_debt", sa.BigInteger()),
    ("total_cash", sa.BigInteger()),
    ("free_cash_flow", sa.BigInteger()),
    ("operating_cash_flow", sa.BigInteger()),
    ("enterprise_value", sa.BigInteger()),
    ("beta", sa.Numeric(10, 4)),
    ("trailing_eps", sa.Numeric(19, 4)),
    ("forward_eps", sa.Numeric(19, 4)),
    ("forward_pe", sa.Numeric(19, 4)),
    ("earnings_growth", sa.Numeric(10, 4)),
    ("payout_ratio", sa.Numeric(10, 4)),
    ("dividend_rate", sa.Numeric(19, 4)),
    # Analist görüşü BAŞKASININ değerlendirmesi. Aktarılabilir bir olgu
    # ("16 analistin ortalama hedefi"), ürünün kendi görüşü değil.
    ("recommendation_key", sa.String(24)),
    ("analyst_count", sa.Integer()),
    ("target_mean_price", sa.Numeric(19, 4)),
    ("ex_dividend_date", sa.DateTime(timezone=True)),
    ("earnings_date", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    for name, type_ in COLUMNS:
        op.add_column(TABLE, sa.Column(name, type_, nullable=True), schema=SCHEMA)


def downgrade() -> None:
    for name, _type in reversed(COLUMNS):
        op.drop_column(TABLE, name, schema=SCHEMA)
