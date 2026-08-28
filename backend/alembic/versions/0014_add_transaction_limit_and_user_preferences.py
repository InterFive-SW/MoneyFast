"""Add transaction_limit and user_preferences columns

İşlem Onay Limiti ve Kullanıcı Tercihleri desteği. Güvenlik Merkezi'ndeki
slider (transaction_limit) ve Görünüm sekmesindeki dil/para birimi/şablon
tercihleri (user_preferences) bu migration ile veritabanına eklenir.

Revision ID: 0014
Revises: 0013_add_notification_preferences
Create Date: 2026-08-27 16:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '0014'
down_revision: Union[str, None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # İşlem Onay Limiti — SMS/2FA doğrulaması gerektiren eşik değeri (₺).
    # Varsayılan 50.000₺; mevcut kullanıcılar otomatik olarak bu değeri alır.
    op.add_column('users', sa.Column(
        'transaction_limit',
        sa.Integer(),
        nullable=False,
        server_default='50000'
    ))

    # Görünüm ve Bölgesel Tercihler — dil, para birimi, dashboard şablonu.
    # JSONB formatında saklanır; yeni tercih eklemek migration gerektirmez.
    op.add_column('users', sa.Column(
        'user_preferences',
        JSONB(),
        nullable=False,
        server_default='{}'
    ))


def downgrade() -> None:
    op.drop_column('users', 'user_preferences')
    op.drop_column('users', 'transaction_limit')
