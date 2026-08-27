"""risk score history

One row per user per day, written as a side effect of reading the risk page.

The uniqueness lives in the schema rather than in a code path someone can
forget: `(user_id, captured_on)` makes a second read on the same day unable to
insert a second row, so the table stays bounded at roughly 365 rows per user
per year without a cleanup job.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "risk_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("captured_on", sa.Date(), nullable=False),
        # Nullable throughout: a day on which something could not be measured
        # is recorded as unmeasured. Zeroes would draw a crash on the chart
        # that the portfolio never had.
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=True),
        sa.Column("volatility", sa.Float(), nullable=True),
        sa.Column("hhi", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("position_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "captured_on", name="uq_risk_snapshots_user_day"),
        schema="risk",
    )
    op.create_index(
        "idx_risk_snapshots_user_day",
        "risk_snapshots",
        ["user_id", "captured_on"],
        schema="risk",
    )


def downgrade() -> None:
    op.drop_index(
        "idx_risk_snapshots_user_day", table_name="risk_snapshots", schema="risk"
    )
    op.drop_table("risk_snapshots", schema="risk")
