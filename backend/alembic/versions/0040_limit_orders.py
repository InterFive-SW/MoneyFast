"""transaction_proposals.limit_price — bekleyen emirler

Revision ID: 0040
Revises: 0039

Limit fiyat bugüne kadar YALNIZCA `payload["estimate"]["reference_price"]`
içinde duruyordu ve orada bir piyasa emrinin referans fiyatından ayırt
edilemiyordu. Bekleyen emirleri her turda tarayan bir iş, JSONB içinde
saklanan bir sayıya göre süzemez; ayrı ve indeksli bir sütun gerekiyor.

`WAITING_PRICE` durumu için kısmi indeks: tarama YALNIZCA bekleyen emirlere
bakıyor ve tablo zamanla gerçekleşmiş emirlerle dolacak.

`expires_at` YENİDEN KULLANILMIYOR: o alan 15 dakikalık HAZIRLAMA TTL'i ve
onaylama süresi geçince 410 dönüyor. Bekleyen bir emir günlerce yaşıyor,
dolayısıyla o alanın anlamını değiştirmek onay kapısını da bozardı.
"""

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

SCHEMA = "investment"


def upgrade() -> None:
    op.add_column(
        "transaction_proposals",
        sa.Column("limit_price", sa.Numeric(19, 6), nullable=True),
        schema=SCHEMA,
    )
    # Kısmi indeks: eşleştirici yalnızca bekleyen emirleri okuyor ve tablo
    # zamanla gerçekleşmiş emirlerle dolacak.
    op.create_index(
        "idx_proposals_waiting",
        "transaction_proposals",
        ["symbol"],
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'WAITING_PRICE'"),
    )


def downgrade() -> None:
    op.drop_index("idx_proposals_waiting", table_name="transaction_proposals", schema=SCHEMA)
    op.drop_column("transaction_proposals", "limit_price", schema=SCHEMA)
