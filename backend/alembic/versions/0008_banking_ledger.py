"""banking accounts and a double-entry transfer ledger

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-20

The banking module was three empty files and a health check, so the assistant
had to refuse every "para gönder" — and before that refusal existed, it staged
transfers through the *investment* path, where they were labelled "Satım",
charged brokerage commission and confirmed into a proposal that moved nothing.

This builds what `infra/intertech.sql:93-140` already designed. The shape is
the point: a transfer is a `transactions` row with two `account_transactions`
legs, each recording `balance_before` and `balance_after`. Storing the balances
is what lets someone reading the history later say what an account held at a
given moment without replaying every movement since it opened. The reference
schema's own comment puts it plainly: the accounts are not the source of truth,
the transactions are.
"""

import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STARTING_BALANCE = 50000


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS banking")

    op.create_table(
        "accounts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False, index=True),
        sa.Column("account_number", sa.String(64), nullable=False, unique=True),
        sa.Column("iban", sa.String(34), nullable=False, unique=True),
        sa.Column("account_type", sa.String(20), nullable=False, server_default="vadesiz"),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="TRY"),
        sa.Column("balance", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="banking",
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("reference_number", sa.String(40), nullable=False, unique=True),
        sa.Column("transaction_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="TRY"),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        schema="banking",
    )

    op.create_table(
        "account_transactions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "transaction_id", sa.String(),
            sa.ForeignKey("banking.transactions.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column(
            "account_id", sa.String(),
            sa.ForeignKey("banking.accounts.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("balance_before", sa.Numeric(19, 4), nullable=False),
        sa.Column("balance_after", sa.Numeric(19, 4), nullable=False),
        sa.Column("counterparty_name", sa.String(255), nullable=True),
        sa.Column("counterparty_iban", sa.String(34), nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="banking",
    )

    # Open a deposit account for everyone who already registered, so existing
    # testers have something to transfer between without re-registering.
    connection = op.get_bind()
    for (user_id,) in connection.execute(
        sa.text("SELECT id FROM users ORDER BY created_at")
    ).fetchall():
        # Same derivation the service uses. Hashed rather than sliced from the
        # id: two users whose ids differ only in their letters would otherwise
        # produce an identical IBAN and collide on its unique constraint.
        digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()
        number = "1" + str(int(digest[:16], 16)).zfill(12)[:12]
        digits = "".join(ch for ch in number if ch.isdigit()).zfill(16)[-16:]
        connection.execute(
            sa.text(
                """
                INSERT INTO banking.accounts
                    (id, user_id, account_number, iban, account_type,
                     currency_code, balance, status, created_at, updated_at)
                VALUES (gen_random_uuid()::text, :uid, :number, :iban, 'vadesiz',
                        'TRY', :balance, 'active', now(), now())
                ON CONFLICT (account_number) DO NOTHING
                """
            ),
            {
                "uid": str(user_id),
                "number": number,
                # TR00 on purpose: a valid check digit would make these look
                # like routable accounts, and nothing here reaches a network.
                "iban": f"TR00{digits}00000{digits[:2]}",
                "balance": STARTING_BALANCE,
            },
        )


def downgrade() -> None:
    op.drop_table("account_transactions", schema="banking")
    op.drop_table("transactions", schema="banking")
    op.drop_table("accounts", schema="banking")
    op.execute("DROP SCHEMA IF EXISTS banking")
