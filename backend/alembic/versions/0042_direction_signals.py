"""Yön okumalarının gecelik hesaplanmış hâli.

Neden bir tablo: Piyasalar ekranı "ölçülen kanıt yönü" kolonuyla
sıralanabiliyor ve 1.011 enstrümanın okumasını istek anında hesaplamak
sembol başına üç sorgu demek. Tek sembol sorulduğunda okuma hâlâ TAZE
hesaplanıyor (`GET /market/direction`); burası yalnızca tarama için.

`evidence` JSONB: tarama satırı da gerekçesini taşımak zorunda, çünkü
gerekçesiz bir yön kullanıcının doğrulayamayacağı bir iddiadır. Alan
sorgulanmıyor, yalnızca okunuyor -- ayrı bir tabloya bölmek her tarama
satırını bir birleştirmeye çevirirdi.

`lean` nullable: ölçülemeyen bir okumada NULL, sıfır değil. Sıfır "ölçtük ve
dengede" demek olurdu ve tarama onu MIXED satırlarla karıştırırdı.

Revision ID: 0042
Revises: 0041
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "direction_signals",
        sa.Column("product_id", sa.String(length=36), primary_key=True),
        sa.Column("horizon", sa.String(length=4), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("lean", sa.Numeric(6, 4), nullable=True),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("observations", sa.Integer(), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="market",
    )
    # Tarama tek bir vadede meyle göre sıralıyor; ikisi birlikte indeksleniyor.
    op.create_index(
        "idx_direction_signals_horizon_lean",
        "direction_signals",
        ["horizon", "lean"],
        schema="market",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_direction_signals_horizon_lean",
        table_name="direction_signals",
        schema="market",
    )
    op.drop_table("direction_signals", schema="market")
