"""credit cards and loans, off the mock

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-27

`CreditCardsWidget`, `CardsView`, `LoansWidget` and `CardSettingsModal` have
been rendering `MOCK_BANKING_DATA` since they were written: a card whose limit
nobody set, a debt nobody owed, and a "pay" button that edited React state.
These are the tables behind them.

Shapes follow the interfaces the UI already defines in `mockBankingData.ts`,
so the screens keep working against real rows rather than being rewritten
around a new model.

Derived values are NOT stored. `availableLimit` is limit minus debt and
`progressPercentage` is what is paid over the total; storing either would let
a card display an available limit that no longer equals its own arithmetic --
the same rule `portfolio_positions` follows for market value.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cards",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("brand", sa.String(length=20), nullable=False, server_default="visa"),
        #: Masked at rest. There is no PAN in this system to mask -- the value
        #: is generated for display -- but storing something that LOOKS like a
        #: card number unmasked teaches the wrong habit.
        sa.Column("card_number", sa.String(length=25), nullable=False),
        sa.Column("credit_limit", sa.Numeric(19, 4), nullable=False),
        sa.Column("current_debt", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("due_day", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("is_digital", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        #: Freeze, online shopping, contactless -- what CardSettingsModal edits.
        sa.Column("settings", sa.dialects.postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("linked_account_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        schema="banking",
    )
    op.create_index("ix_cards_user", "cards", ["user_id"], schema="banking")

    op.create_table(
        "loans",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("principal", sa.Numeric(19, 4), nullable=False),
        sa.Column("remaining_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("installment_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("installment_count", sa.Integer(), nullable=False),
        sa.Column("paid_installments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_due", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        schema="banking",
    )
    op.create_index("ix_loans_user", "loans", ["user_id"], schema="banking")


def downgrade() -> None:
    op.drop_table("loans", schema="banking")
    op.drop_table("cards", schema="banking")
