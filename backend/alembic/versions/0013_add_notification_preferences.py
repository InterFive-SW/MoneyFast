"""Add notification_preferences JSONB

Revision ID: 0013_add_notification_preferences
Revises: 0012
Create Date: 2026-08-27 15:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add notification_preferences column with server_default
    op.add_column(
        'users',
        sa.Column(
            'notification_preferences',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False
        )
    )
    # 2. Drop wants_email_notifications
    op.drop_column('users', 'wants_email_notifications')


def downgrade() -> None:
    # 1. Add back wants_email_notifications
    op.add_column(
        'users',
        sa.Column('wants_email_notifications', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False)
    )
    # 2. Drop notification_preferences
    op.drop_column('users', 'notification_preferences')
