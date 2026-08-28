"""staged payments, so the chat can propose without moving money

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-26

The investment side already has this contract: the assistant stages a
proposal, the user presses Onayla, and only then does anything happen. Money
movement needs the same guarantee -- a chatbot that can pay a bill on its own
reading of "evet" is a chatbot that can empty an account on a misheard word.

A separate table from `investment.transaction_proposals` on purpose. A model
belongs to the module that owns it (CLAUDE.md, "shared/ kuralı"), and that
table's columns are `symbol`, `quantity`, `order_type` -- a bill payment
answering those with NULL would be a row shaped like an order that is not one,
which is the confusion the staging contract exists to prevent.

`id` is derived from the idempotency key, so a retried staging call resolves
to the same row instead of stacking proposals against one balance.
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
        "payment_proposals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        #: TRANSFER | BILL_PAYMENT | CARD_PAYMENT. One staging path for every
        #: way money leaves an account, so there is one confirm to audit.
        sa.Column("payment_type", sa.String(length=20), nullable=False),
        sa.Column("source_account_id", sa.String(length=64), nullable=True),
        #: IBAN, subscriber number or card reference, depending on the type.
        sa.Column("destination_reference", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="TRY"),
        #: What was staged, verbatim. The confirm screen shows this rather than
        #: re-deriving figures that may have moved since.
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("audit_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="banking",
    )
    op.create_index(
        "ix_payment_proposals_user", "payment_proposals",
        ["user_id", "created_at"], schema="banking",
    )


def downgrade() -> None:
    op.drop_table("payment_proposals", schema="banking")
