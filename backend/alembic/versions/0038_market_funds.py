"""market.funds ve market.fund_prices — TEFAS

Revision ID: 0038
Revises: 0037

`Fonlar` ekranı `MOCK_FUNDS` üzerinden çiziliyordu. Bu iki tablo onu gerçek
veriyle değiştiriyor.

**Sütunlar TEFAS'ın gerçekten verdiği kadar.** Arayüzün mock'ta okuduğu
yönetim ücreti, stopaj, risk değeri ve hisse bazında portföy dağılımı
TEFAS API'sinde YOK -- HAR kaydındaki 85 alanın hepsi tarandı. Onlar için
sütun açılmadı: boş bir sütun, bir gün dolacakmış gibi duran bir söz olurdu
ve deponun kuralı zaten *"aracın hiç döndürmediği bir alan için `veri yok`
kullanılmaz"*.

`fund_prices` ayrı bir tablo çünkü ayrı bir erişim deseni: `funds` "bugün ne
durumda" sorusuna tek satırla cevap veriyor, `fund_prices` ise bir seri ve
yalnızca grafik okuyor. `market_quotes`/`market_candles` ayrımının aynısı.
"""

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

SCHEMA = "market"


def upgrade() -> None:
    op.create_table(
        "funds",
        # Fon kodu birincil anahtar: TEFAS'ın kendi kimliği, üç harf, ve
        # ayrı bir yüzey id'si üretmek iki kimlik arasında eşleme tutmak
        # demek olurdu.
        sa.Column("code", sa.String(16), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        #: Kurucu / PYŞ. Ekrandaki süzgecin tamamı. Bilinmiyorsa NULL --
        #: fon yine listeleniyor, yalnızca o süzgeçle bulunamıyor.
        sa.Column("founder", sa.String(200), nullable=True),
        sa.Column("operator", sa.String(200), nullable=True),
        #: Şemsiye türü. Fon başına ayrı bir istek gerektirdiği için
        #: bütçeyle dolduruluyor; henüz çekilmemiş fonda NULL.
        sa.Column("umbrella", sa.String(120), nullable=True),
        #: YAT / EMK / BYF.
        sa.Column("fund_type", sa.String(8), nullable=True),
        sa.Column("price", sa.Numeric(19, 6), nullable=True),
        sa.Column("shares", sa.Numeric(24, 2), nullable=True),
        sa.Column("investors", sa.Integer(), nullable=True),
        sa.Column("size", sa.Numeric(24, 2), nullable=True),
        #: Fiyatın ait olduğu gün. Fon fiyatı GÜNLÜKTÜR; bir zaman damgası
        #: taşımak, olmayan bir anlık değeri varmış gibi gösterirdi.
        sa.Column("as_of", sa.Date(), nullable=True),
        #: TEFAS'ta pasif görünen fon SİLİNMİYOR: geçmişi olan bir fonu
        #: silmek, onu tutmuş kullanıcının geçmişini de silmek olurdu.
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        schema=SCHEMA,
    )
    # Ekranın üç süzgeci de sunucuda çalışıyor: 2.602 fonu tarayıcıya
    # göndermek yerine sorgulanıyorlar.
    op.create_index("idx_funds_founder", "funds", ["founder"], schema=SCHEMA)
    op.create_index("idx_funds_umbrella", "funds", ["umbrella"], schema=SCHEMA)
    op.create_index("idx_funds_type", "funds", ["fund_type"], schema=SCHEMA)

    op.create_table(
        "fund_prices",
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("price", sa.Numeric(19, 6), nullable=False),
        # Aynı fonun aynı günü iki kez yazılamaz: seri yeniden çekildiğinde
        # tur bir no-op olmalı, ikinci bir kopya değil.
        sa.PrimaryKeyConstraint("code", "as_of", name="pk_fund_prices"),
        schema=SCHEMA,
    )
    op.create_index(
        "idx_fund_prices_code_time", "fund_prices", ["code", "as_of"], schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("fund_prices", schema=SCHEMA)
    op.drop_table("funds", schema=SCHEMA)
