"""market.funds — kategori ölçüleri

Revision ID: 0039
Revises: 0038

TEFAS'ın DÖNDÜRDÜĞÜ ama atılan üç alan. Hiçbiri hesaplanmış değil; üçü de
TEFAS'ın kendi ölçümü:

* `category_rank` / `category_size` — `fonFiyatBilgiGetir`in
  `kategoriDerece` / `kategoriFonSay` alanları. "86 para piyasası fonu
  içinde 71." Bir fonun getirisinin iyi mi kötü mü olduğunu tek başına
  getiri söylemiyor; sıra söylüyor.
* `category_return` — `fonProfilDtyGetir`in `fonTurGetiri` alanı,
  kategorinin ortalama getirisi. %38'in iyi olup olmadığı ancak kategori
  %41 yaptıysa cevaplanabiliyor.

Üçü de NULL olabiliyor: henüz çekilmemiş fonda değer yok ve sıfır yazmak
"kategorisinde birinci" ya da "kategorisi hiç kazandırmadı" demek olurdu.
"""

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

SCHEMA = "market"


def upgrade() -> None:
    op.add_column("funds", sa.Column("category_rank", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column("funds", sa.Column("category_size", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column(
        "funds", sa.Column("category_return", sa.Numeric(12, 4), nullable=True), schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("funds", "category_return", schema=SCHEMA)
    op.drop_column("funds", "category_size", schema=SCHEMA)
    op.drop_column("funds", "category_rank", schema=SCHEMA)
