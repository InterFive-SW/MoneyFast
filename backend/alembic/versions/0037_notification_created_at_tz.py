"""notifications.created_at -> timestamptz

Revision ID: 0037
Revises: 0036

Şemadaki TEK naive zaman sütunuydu. Değer her zaman UTC olarak yazılıyordu
(`default=lambda: datetime.now(timezone.utc)`) ama sütun offset'i düşürdüğü
için `created_at` API'den `Z` OLMADAN çıkıyor. ECMAScript'e göre offset'siz
bir tarih-saat dizesi YEREL saat sayılır, dolayısıyla tarayıcı UTC bir anı
Istanbul saati sanıyor ve bildirim saatleri üç saat kaymış görünüyordu.

Ön yüzü düzeltmek tek başına yetmezdi: değer yanlış etiketle geldiği sürece
hangi dilimde biçimlendirildiği fark etmiyor.

`USING created_at AT TIME ZONE 'UTC'` mevcut satırları ETİKETLİYOR,
KAYDIRMIYOR: naive değerler zaten UTC'ydi, bu dönüşüm onlara doğru dilimi
veriyor. Geri alma da aynı şekilde simetrik.
"""

from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

#: `notifications` varsayılan şemada -- modelde `__table_args__` yok.
#: Ölçüldü: information_schema `public` diyor.
SCHEMA = "public"


def upgrade() -> None:
    op.alter_column(
        "notifications",
        "created_at",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.alter_column(
        "notifications",
        "created_at",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
        schema=SCHEMA,
    )
