"""per-user investment accounts, so a trade can actually settle

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-20

Confirming a trade used to set two columns on the proposal row and commit.
No cash moved, no position changed — yet the order list then displayed
"Gerçekleşti" for a trade that changed nothing, which FOG-GB-01 (no data
inconsistency in financial operations) and FOG-GB-02 (executed operations
shown clearly) both forbid.

Settlement needs somewhere to settle *to*, and there was exactly one account
row — `user_id = 'demo'`, shared by every user — so "deduct the buyer's cash"
had no buyer to deduct from. This migration gives each user their own account.

Two deliberate choices:

* **Existing users get the demo holdings copied in, not moved.** This is a
  demo system with synthetic positions; leaving the new accounts empty would
  mean every existing tester logs in to a blank portfolio and cannot exercise
  a sell. The quantities were always fictional (see 0006) — what changes is
  that the fiction is now per-user instead of shared.
* **`TR-DEMO-0001` stays.** Anonymous callers still resolve to it, so the
  public endpoints keep working without a token.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Opening cash for a new account, matching the demo account seeded in 0006.
STARTING_CASH = 25000


def upgrade() -> None:
    connection = op.get_bind()

    users = connection.execute(
        sa.text("SELECT id FROM users ORDER BY created_at")
    ).fetchall()

    for index, (user_id,) in enumerate(users, start=1):
        existing = connection.execute(
            sa.text(
                "SELECT id FROM investment.investment_accounts WHERE user_id = :uid"
            ),
            {"uid": str(user_id)},
        ).first()
        if existing is not None:
            continue

        account_number = f"TR-{index:04d}-{str(user_id)[:8].upper()}"
        connection.execute(
            sa.text(
                """
                INSERT INTO investment.investment_accounts
                    (id, user_id, account_number, name, currency_code,
                     cash_balance, status, created_at)
                VALUES (gen_random_uuid()::text, :uid, :number, 'Yatırım Hesabı',
                        'TRY', :cash, 'active', now())
                ON CONFLICT (account_number) DO NOTHING
                """
            ),
            {"uid": str(user_id), "number": account_number, "cash": STARTING_CASH},
        )

        # Copy the demo holdings so an existing tester keeps a portfolio to
        # trade against. New registrations start empty — see auth service.
        connection.execute(
            sa.text(
                """
                INSERT INTO investment.portfolio_positions
                    (id, investment_account_id, product_id, quantity,
                     average_buy_price, opened_at, updated_at)
                SELECT gen_random_uuid()::text, target.id, p.product_id,
                       p.quantity, p.average_buy_price, p.opened_at, now()
                FROM investment.portfolio_positions p
                JOIN investment.investment_accounts demo
                  ON demo.id = p.investment_account_id
                 AND demo.account_number = 'TR-DEMO-0001'
                CROSS JOIN LATERAL (
                    SELECT id FROM investment.investment_accounts
                    WHERE account_number = :number
                ) AS target
                ON CONFLICT ON CONSTRAINT uq_portfolio_positions_holding DO NOTHING
                """
            ),
            {"number": account_number},
        )


def downgrade() -> None:
    # Positions cascade from the account rows.
    op.execute(
        """
        DELETE FROM investment.investment_accounts
        WHERE account_number <> 'TR-DEMO-0001'
        """
    )
