"""align users table with the auth ORM

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-20

Migration 0001 created `full_name`, but `app/modules/auth/models.py` declares
`tc_no`, `first_name`, `last_name` and `phone_number`. Every call into
`auth/service.py` therefore raised UndefinedColumn against a migrated
database: registration and login were both broken, and nothing exercised them
until the chat work needed a real session.

This migration makes the table match the ORM. It is written to survive a
developer database that already holds rows, even though the reference database
was empty when it was authored:

* `first_name` / `last_name` are split out of `full_name` on the first space.
* `tc_no` has no source to recover from, so orphan rows get a deterministic
  placeholder using the project's existing dummy convention -- the "999"
  prefix from `backend/scripts/generate_dummy_data.py`. Such a value is
  obviously fake at a glance, which is the point.
* `phone_number` likewise gets an unmistakably fake placeholder.

Backfilling before the NOT NULL constraints is what keeps this safe on a
non-empty table; on an empty one the UPDATEs are simply no-ops.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Matches DUMMY_TC_PREFIX in backend/scripts/generate_dummy_data.py.
DUMMY_TC_PREFIX = "999"


def upgrade() -> None:
    # 1. Add nullable, so an existing row does not block the DDL.
    op.add_column("users", sa.Column("tc_no", sa.String(), nullable=True))
    op.add_column("users", sa.Column("first_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("phone_number", sa.String(), nullable=True))

    # 2. Backfill. split_part returns '' rather than NULL when there is no
    #    separator, so a single-word full_name yields a first name and an
    #    empty last name instead of a constraint violation.
    op.execute(
        """
        UPDATE users
        SET first_name = COALESCE(NULLIF(split_part(full_name, ' ', 1), ''), 'Bilinmeyen'),
            last_name  = COALESCE(
                NULLIF(substring(full_name from position(' ' in full_name) + 1), ''),
                'Kullanıcı'
            )
        WHERE first_name IS NULL
        """
    )
    # row_number keeps the placeholder unique without depending on the id
    # format, which is a bare string column rather than a real UUID type.
    op.execute(
        f"""
        UPDATE users AS u
        SET tc_no = '{DUMMY_TC_PREFIX}' || lpad(seq.rn::text, 8, '0'),
            phone_number = COALESCE(u.phone_number, '+90555' || lpad(seq.rn::text, 6, '0'))
        FROM (SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM users) AS seq
        WHERE u.id = seq.id AND u.tc_no IS NULL
        """
    )

    # 3. Now the constraints can land.
    op.alter_column("users", "tc_no", nullable=False)
    op.alter_column("users", "first_name", nullable=False)
    op.alter_column("users", "last_name", nullable=False)
    op.alter_column("users", "phone_number", nullable=False)
    op.create_index(op.f("ix_users_tc_no"), "users", ["tc_no"], unique=True)

    # 4. The column the ORM never knew about.
    op.drop_column("users", "full_name")


def downgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(), nullable=True))
    op.execute("UPDATE users SET full_name = btrim(first_name || ' ' || last_name)")
    op.alter_column("users", "full_name", nullable=False)

    op.drop_index(op.f("ix_users_tc_no"), table_name="users")
    op.drop_column("users", "phone_number")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
    op.drop_column("users", "tc_no")
