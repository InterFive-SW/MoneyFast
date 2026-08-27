"""risk tolerance profile and assessments

Creates the `risk` schema and the two tables behind the questionnaire.

`infra/intertech.sql` sketches these under `auth`. They land under `risk`
instead because CLAUDE.md puts a model in the module that owns it, and `auth`
owns identity rather than risk tolerance. `user_id` carries no foreign key, the
same way `ai.conversations` references a user: one database, no import graph
between modules.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS risk")

    # Append-only history. Every submission is kept so a changed tolerance is
    # visible as a change rather than as a silent overwrite, and so an old
    # score is never re-derived under new weights.
    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("questionnaire_version", sa.String(length=16), nullable=False),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
        sa.Column("raw_score", sa.Float(), nullable=False),
        sa.Column("tolerance_level", sa.String(length=16), nullable=False),
        sa.Column("investment_horizon", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="risk",
    )
    op.create_index(
        "idx_risk_assessments_user_created",
        "risk_assessments",
        ["user_id", "created_at"],
        schema="risk",
    )

    # The tolerance in effect. Keyed on the user: a second row would mean two
    # answers to "what do you tolerate" and nothing could say which one the
    # comparison used.
    op.create_table(
        "risk_profiles",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("tolerance_level", sa.String(length=16), nullable=False),
        sa.Column("investment_horizon", sa.String(length=32), nullable=False),
        sa.Column("latest_assessment_id", sa.String(), nullable=False),
        sa.Column("questionnaire_version", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
        schema="risk",
    )


def downgrade() -> None:
    op.drop_table("risk_profiles", schema="risk")
    op.drop_index(
        "idx_risk_assessments_user_created", table_name="risk_assessments", schema="risk"
    )
    op.drop_table("risk_assessments", schema="risk")
    op.execute("DROP SCHEMA IF EXISTS risk")
