"""Uygunluk testinin ürün grubu sonucu, yürürlükteki profilde.

Uygunluk testi v2 ürün grubu başına bir yeterlilik üretiyor: bu kişiye mevduat,
tahvil, hisse ve türev gruplarından hangileri sunulabilir. Bu sonuç profilde
denormalize duruyor -- `tolerance_level` da öyle ve aynı sebeple: yürürlükteki
profili okumak her seferinde değerlendirme satırına bir birleştirme
gerektirmemeli.

NULL BIRAKILIYOR, boş listeye çevrilmiyor. İkisi farklı şeyler söylüyor: null
"bu profil v1 ile dolduruldu, ürün grubu hiç sorulmadı", boş liste ise
"soruldu, hiçbiri uygun çıkmadı". Mevcut profillerin hepsi birincisi ve
ikincisini yazmak, o kullanıcılar hakkında verilmemiş bir karar uydurmak
olurdu.

Geri alınabilir: kolon düşer, hiçbir eski satır etkilenmez.

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-02 12:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "risk_profiles",
        sa.Column("product_groups", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="risk",
    )


def downgrade() -> None:
    op.drop_column("risk_profiles", "product_groups", schema="risk")
