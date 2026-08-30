"""Üst şeride EUR/USD paritesi.

Bandda gösterilmesi istenen dört temel değerden üçü zaten evrende: USDTRY,
EURTRY ve XAUUSD. Eksik olan EUR/USD.

Altının TL karşılığı için ayrı bir enstrüman EKLENMİYOR: sağlayıcı `XAUTRY=X`
için fiyat döndürmüyor (2026-08-29'da denendi, boş geldi). Altın kendi para
biriminde gösterilip yanına canlı USDTRY kuruyla yaklaşık TL karşılığı
yazılıyor -- `frontend/src/lib/money.ts`'in bütün uygulamada uyguladığı kural.
Olmayan bir beslemeyi varmış gibi tohumlamak, fiyatlanamayan bir adı
tohumlamakla aynı hata olurdu (bkz. 0010'un ANSS/EA kararı).

`EURUSD=X` sağlayıcıya sorulup fiyat döndürdüğü doğrulandı (1,1587).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO investment.investment_products "
            "(id, symbol, data_symbol, name, product_type, market, currency_code, "
            " status, created_at, updated_at) "
            "VALUES (gen_random_uuid()::text, 'EURUSD', 'EURUSD=X', "
            "        'Euro / ABD Doları', 'fx', 'FX', 'USD', 'active', now(), now()) "
            "ON CONFLICT (symbol) DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM investment.investment_products WHERE symbol = 'EURUSD'")
    )
