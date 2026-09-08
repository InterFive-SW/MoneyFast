"""Ölçülen risk bandının kova hedefi.

Yeniden dengeleme, hedefini iki yerden alabiliyor: kullanıcının kendi
`allocation_targets` satırları, ya da -- kullanıcı hiç hedef koymamışsa --
bağlayıcı bandın bu matristeki karşılığı. Kullanıcının kendi hedefi her
zaman kazanıyor.

**Değerler, bugüne kadar arayüzde şablon olarak sunulan üç karışımın
kendisi.** `allocation.TEMPLATES` (Ağırlıklı nakit / Dengeli / Ağırlıklı
hisse) sırasıyla Düşük / Orta / Yüksek bandına karşılık geliyor; yeni olan
tek satır `Risksiz`. Yeni sayı uydurulmadı: şablonların ağırlıkları zaten
gerekçelendirilmişti, değişen tek şey kullanıcının bir ad seçmesi yerine
ölçüm ile beyanın bağlayıcı bandının seçmesi.

`Risksiz` bandı, ölçülen volatilitesi tabanın altında kalan bir portföyün
karşılığı; hisse ağırlığı yalnızca beş puan ve ABD hissesi HİÇ YOK -- satırı
olmayan kova, hedefi olmayan kova demek.

**Sıfırlık satır YAZILMIYOR.** Bir kovaya %0 hedefi koymak "o kovadaki her
şeyi sat" demek olurdu; satırın hiç olmaması ise "bu bandın o kova hakkında
bir görüşü yok". `allocation.drift()` ikisini zaten ayırıyor. Bu yüzden
Yüksek bandında `fx`, Risksiz ve Düşük bandında `us_equity` satırı yok.

Her bandın YAZILI satırları 100'e topluyor.

Revision ID: 0046
Revises: 0045
"""

from alembic import op
import sqlalchemy as sa

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

#: (bant, kova, hedef yüzdesi). Elle yazılı ve tarihli -- bir hedef matrisi
#: çalışma anında değişen bir şey değil, ve değiştiğinde bunun diff'te
#: okunabilir olması gerekiyor.
TARGETS = [
    ("Risksiz", "cash", 80), ("Risksiz", "bist_equity", 5),
    ("Risksiz", "gold", 10), ("Risksiz", "fx", 5),

    ("Düşük", "cash", 60), ("Düşük", "bist_equity", 20),
    ("Düşük", "gold", 10), ("Düşük", "fx", 10),

    ("Orta", "cash", 25), ("Orta", "bist_equity", 30),
    ("Orta", "us_equity", 20), ("Orta", "gold", 15), ("Orta", "fx", 10),

    ("Yüksek", "cash", 10), ("Yüksek", "bist_equity", 45),
    ("Yüksek", "us_equity", 35), ("Yüksek", "gold", 10),
]


def upgrade() -> None:
    op.create_table(
        "risk_band_targets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("band", sa.String(length=16), nullable=False),
        sa.Column("bucket", sa.String(length=32), nullable=False),
        sa.Column("target_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("band", "bucket", name="uq_risk_band_target_bucket"),
        schema="investment",
    )
    op.execute(
        "INSERT INTO investment.risk_band_targets (id, band, bucket, target_percent) "
        "VALUES "
        + ", ".join(
            f"(gen_random_uuid()::text, '{band}', '{bucket}', {percent})"
            for band, bucket, percent in TARGETS
        )
    )


def downgrade() -> None:
    op.drop_table("risk_band_targets", schema="investment")
