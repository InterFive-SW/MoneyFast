"""users.is_verified

The column the auth ORM has been declaring since the SMTP work landed on main
(PR #35), which no migration ever created.

Without it the application does not start in any useful sense: `User` selects
every mapped column, so the very first query -- the one behind
`POST /api/auth/login` -- fails with `UndefinedColumn: users.is_verified does
not exist` and the endpoint returns 500. It is also why eleven auth tests fail
on main today.

Defaulted to false, which is what the ORM declares, so the column and the
model agree from here on.

Rows that already exist ARE backfilled to true, and that is a deliberate
reading rather than a convenience. A row written before this column existed
did not fail verification -- there was nothing to verify against, no mail was
ever sent, and no token was ever issued. Leaving them false would lock every
account created before today out of an application whose login path now
refuses an unverified user with a 403, with no way back in while SMTP is not
configured locally. The team's own reference data agrees: all eleven files in
`seeds/` write is_verified TRUE for exactly these accounts.

Accounts created AFTER this migration go through `create_user`, which sets
False explicitly, so the verification flow is untouched.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_verified",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.execute("UPDATE users SET is_verified = true")


def downgrade() -> None:
    op.drop_column("users", "is_verified")
