"""a separate admin identity, not a privileged customer

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-26

An admin here is not a customer with extra powers. It cannot hold a portfolio,
place an order or open the chat; its whole purpose is to look after customer
accounts without anyone opening psql. So it gets its own table rather than a
`role` column on `public.users`.

That choice is the security property. With a role column there exists a row
that can be escalated into an admin by flipping one value, and every customer
endpoint has to remember to check it. With a separate table there is no such
row: an admin subject simply does not resolve in `User`, so the customer side
refuses it without being asked to.

The seeded account exists because a migration that creates a login nobody can
use is not a feature. Credentials are demo credentials, in a system whose data
is entirely synthetic (CLAUDE.md).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from passlib.context import CryptContext

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Demo administrator. Synthetic, like every other credential in this project.
SEED_ADMIN_USERNAME = "admin"
SEED_ADMIN_PASSWORD = "Admin123!"
SEED_ADMIN_NAME = "Sistem Yöneticisi"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS admin")

    op.create_table(
        "admin_users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("username", name="uq_admin_users_username"),
        schema="admin",
    )

    # Hashed with the same passlib context the customer side uses, so there is
    # one password policy in the system rather than two.
    hashed = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(SEED_ADMIN_PASSWORD)
    op.execute(
        sa.text(
            "INSERT INTO admin.admin_users (id, username, hashed_password, full_name)"
            " VALUES (gen_random_uuid()::text, :u, :p, :n)"
            " ON CONFLICT (username) DO NOTHING"
        ).bindparams(u=SEED_ADMIN_USERNAME, p=hashed, n=SEED_ADMIN_NAME)
    )


def downgrade() -> None:
    op.drop_table("admin_users", schema="admin")
    op.execute("DROP SCHEMA IF EXISTS admin CASCADE")
