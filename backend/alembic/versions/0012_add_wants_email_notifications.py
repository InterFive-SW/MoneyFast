"""add wants_email_notifications

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-26 18:59:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('wants_email_notifications', sa.Boolean(), server_default='true', nullable=False))


def downgrade():
    op.drop_column('users', 'wants_email_notifications')
