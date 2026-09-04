"""banking.accounts.nickname — kullanıcının hesabına verdiği ad

Revision ID: 0036
Revises: 0035

Arayüzdeki "Yeni Hesap Aç" sihirbazı üçüncü adımda bir hesap adı soruyor ve
dördüncü adımdaki özette gösteriyordu. Saklanacak sütun yoktu: ad hiçbir yere
yazılmıyordu. Sorulup atılan bir girdi, hiç sorulmamasından kötü -- kullanıcı
verdiği adı listede aramaya başlıyor.

Nullable: mevcut hesapların adı yok ve olmadığı için uydurulmuyor. Adı
olmayan hesap listede türünden ve para biriminden türetilen etiketle
görünüyor, bugün olduğu gibi.
"""

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("nickname", sa.String(60), nullable=True),
        schema="banking",
    )


def downgrade() -> None:
    op.drop_column("accounts", "nickname", schema="banking")
