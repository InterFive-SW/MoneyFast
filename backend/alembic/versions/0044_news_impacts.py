"""Haberin bir enstrümana etkisi hakkında yapılandırılmış yargı.

Neden bir tablo ve neden düzyazı değil: bu yargıyı LLM üretiyor. Bir modelin
ürettiği metin denetlenemez -- satır olarak saklandığında her iddia belirli
bir habere kadar izlenebiliyor, günlük özet KODDA toplanabiliyor ve toplayıcı
test edilebiliyor.

`(news_id, symbol)` üzerinde tekil indeks: aynı haber aynı enstrüman için iki
kez yargılanmaz. İş yeniden çalıştırılabilir olmalı ve ikinci bir yargı,
birinciyle çelişse bile sessizce yanına eklenirdi.

`confidence` NUMERIC(4,3): modelin kendi beyanı, bir ölçüm değil. Sıralamada
kullanılıyor, kullanıcıya sayı olarak gösterilmiyor.

Revision ID: 0044
Revises: 0043
"""

from alembic import op
import sqlalchemy as sa

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_impacts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("news_id", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("scope", sa.String(length=12), nullable=False, server_default="DIRECT"),
        sa.Column("magnitude", sa.String(length=8), nullable=False, server_default="LOW"),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0.5"),
        sa.Column("mechanism", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column(
            "analyzed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="market",
    )
    op.create_index(
        "uq_news_impacts_news_symbol",
        "news_impacts",
        ["news_id", "symbol"],
        unique=True,
        schema="market",
    )
    op.create_index(
        "idx_news_impacts_symbol_time",
        "news_impacts",
        ["symbol", "published_at"],
        schema="market",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_news_impacts_symbol_time", table_name="news_impacts", schema="market"
    )
    op.drop_index(
        "uq_news_impacts_news_symbol", table_name="news_impacts", schema="market"
    )
    op.drop_table("news_impacts", schema="market")
