"""news_items.related_symbols üzerinde GIN indeksi

Revision ID: 0035
Revises: 0034

`portfolio_news` ve artık `latest_news` de bu sütunda `overlap` (`&&`)
çalıştırıyor. Dizi üzerinde çakışma sorgusu B-tree ile hızlanmaz; indekssiz
hâlde her sorgu tabloyu baştan sona okuyor. Ölçüldüğünde tablo 29 bin satırdı
ve tarama ucuzdu, ama bu sayı yalnızca büyüyor -- ve `latest_news`'e sembol
süzgeci eklenmesiyle aynı desen artık her hisse detay sayfasında da çalışıyor.

`idx_news_items_published` duruyor: o, süzgeçsiz "en yeni 20" sorgusunun
sıralamasını karşılıyor ve ikisi farklı soruları yanıtlıyor.
"""

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_news_items_related_symbols",
        "news_items",
        ["related_symbols"],
        schema="market",
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_news_items_related_symbols",
        table_name="news_items",
        schema="market",
    )
