"""Vadeli hesaba gerçek faiz: oran, vade ve işletme kaydı.

Arayüz vadeli hesabın yanına `%42.50` ve `32 Gün` yazıyordu; ikisi de
`AccountsView.tsx` içinde sabit metindi ve kaynak dosyanın kendisi bunu
`Vadeli Ekstra Alanları Mock` diye işaretliyordu. Şemada faizle ilgili hiçbir
sütun yoktu, hiçbir yerde de faiz işletilmiyordu -- yani "32 gün sonra ne
olacak" sorusunun cevabı "hiçbir şey"di: bakiye olduğu yerde kalırdı.

Ürün günlük hesaba çevriliyor: vade bir gün, oran da buna göre biraz daha
düşük (%38,00'e karşı %42,50). Daha kısa bağlanmaya daha az ödenmesi, vadeli
hesabın var olma sebebinin ta kendisi.

Faiz, bakiyeyi sessizce büyüterek değil, gerçek bir hareket olarak yazılıyor
(`transaction_type='faiz'`), dolayısıyla hesap dökümü paranın nereden geldiğini
açıklayabiliyor.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Günlük vadeli hesabın yıllık brüt oranı.
DAILY_RATE = 38.000

#: Vade, gün. Bir gün: hesap her gün sonunda işler ve ertesi gün yeniden bağlanır.
DAILY_TERM = 1


def upgrade() -> None:
    op.add_column(
        "accounts", sa.Column("interest_rate", sa.Numeric(6, 3), nullable=True),
        schema="banking",
    )
    op.add_column(
        "accounts", sa.Column("term_days", sa.Integer(), nullable=True),
        schema="banking",
    )
    op.add_column(
        "accounts", sa.Column("last_accrued_at", sa.DateTime(timezone=True), nullable=True),
        schema="banking",
    )

    # Mevcut vadeli hesaplar ürüne geçiriliyor. `last_accrued_at` bilerek boş
    # bırakılıyor: ilk işletme, hesabın açılışından bugüne kadarki günleri
    # değil YALNIZCA bir günü öder. Geçmişe dönük faiz, hiç vaat edilmemiş bir
    # parayı ödemek olurdu.
    op.execute(
        sa.text(
            "UPDATE banking.accounts "
            "   SET interest_rate = :rate, term_days = :term "
            " WHERE account_type IN ('vadeli', 'birikim')"
        ).bindparams(rate=DAILY_RATE, term=DAILY_TERM)
    )


def downgrade() -> None:
    op.drop_column("accounts", "last_accrued_at", schema="banking")
    op.drop_column("accounts", "term_days", schema="banking")
    op.drop_column("accounts", "interest_rate", schema="banking")
