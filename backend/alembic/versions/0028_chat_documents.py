"""Sohbete yüklenen belgelerin kaydı.

Metnin kendisi burada DEĞİL: o, gömülmüş hâliyle vektör veritabanında ve
sahibi yükleyen kullanıcı (vector-migrations 0004). Bu tablo kullanıcının
"Belgelerim" listesinde gördüğü ve sildiği şey.

İki yerde tutulmasının sebebi listeleme ve silme: arayüz için vektör
veritabanına sorgu atmak, uygulama verisini oraya taşımak olurdu.

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-31 13:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0028'
down_revision: Union[str, None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        # Belge kullanıcıya ait, sohbete değil: silinen bir sohbet
        # kullanıcının belgesini götürmemeli.
        sa.Column("thread_id", sa.String(64), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=True),
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        # `rag.documents.id`. Foreign key DEĞİL -- ayrı bir veritabanı.
        sa.Column("rag_document_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="ai",
    )
    op.create_index(
        "idx_chat_documents_user_created",
        "chat_documents",
        ["user_id", "created_at"],
        schema="ai",
    )


def downgrade() -> None:
    op.drop_index("idx_chat_documents_user_created", table_name="chat_documents", schema="ai")
    op.drop_table("chat_documents", schema="ai")
