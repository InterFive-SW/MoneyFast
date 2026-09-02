"""allocation targets — kullanıcının kendi hedef dağılımı

Revision ID: 0033
Revises: 0032
"""

from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "allocation_targets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        # Kova ANAHTARI, etiketi değil: bir etiketi düzeltmek kimsenin
        # kayıtlı hedefini geçersizleştirmemeli.
        sa.Column("bucket", sa.String(32), nullable=False),
        sa.Column("target_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Kova başına tek hedef. İkinci bir satır, hangisinin geçerli olduğunu
        # söyleyemeyen bir hedef bırakırdı.
        sa.UniqueConstraint("user_id", "bucket", name="uq_allocation_target_bucket"),
        schema="investment",
    )
    op.create_index(
        "ix_allocation_targets_user_id",
        "allocation_targets",
        ["user_id"],
        schema="investment",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_allocation_targets_user_id", table_name="allocation_targets",
        schema="investment",
    )
    op.drop_table("allocation_targets", schema="investment")
