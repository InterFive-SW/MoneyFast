"""Administrator identity.

Deliberately its own table in its own schema, not a `role` column on
`public.users`. An admin here is not a customer with extra powers: it holds no
portfolio, places no orders and cannot open the chat. Its only job is to look
after customer accounts without anyone opening psql.

That separation is the security property rather than a tidiness preference.
With a role column there exists a customer row that becomes an admin by
flipping one value, and every customer endpoint has to remember to check it.
With a separate table there is no such row -- `get_current_user` resolves
`sub` against `User.tc_no` and simply finds nothing, so the customer side
refuses an admin token without being asked to.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SCHEMA = "admin"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AdminUser(Base):
    __tablename__ = "admin_users"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
