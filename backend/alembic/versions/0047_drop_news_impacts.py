"""`market.news_impacts` emekliye ayrılıyor.

Tablo, haber yorumlarını bir toplu işin ürettiği ve satır satır sakladığı
mimariye aitti. Bölüm 12'nin tasarımında böyle bir tablo YOK: olgular istek
anında ölçülüyor (`impact.fact_package`) ve yorumu sohbet turunun kendisi
kuruyor -- uygunluk kapısından geçerek.

Neden saklanmıyor da düşürülüyor: saklanan bir yargı, üretildiği tur ve o
turun kuralları geçtikten sonra da okunabilir kalır. Bir sonraki okuyucu onu
bugünün kurallarıyla değerlendirilmiş sanır. Emekliye ayrılan bir mimarinin
verisini "belki lazım olur" diye bırakmak, tam olarak bu yanlış anlamayı
davet ediyor.

Kaybedilen şey ölçülü: yalnızca model yargıları. Haberlerin kendisi
`market.news_items`ta duruyor ve hiçbir satırı bu migration'dan
etkilenmiyor.

`downgrade` tabloyu geri kuruyor ama İÇERİĞİNİ getirmiyor -- geri alınan bir
şema, geri alınmış bir veri değil ve bunu ima etmek yanıltıcı olurdu.

Revision ID: 0047
Revises: 0046
"""

from alembic import op
import sqlalchemy as sa

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("news_impacts", schema="market")


def downgrade() -> None:
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
            "analyzed_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="market",
    )
    op.create_index(
        "uq_news_impacts_news_symbol", "news_impacts", ["news_id", "symbol"],
        unique=True, schema="market",
    )
    op.create_index(
        "idx_news_impacts_symbol_time", "news_impacts", ["symbol", "published_at"],
        schema="market",
    )
