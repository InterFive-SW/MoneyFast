"""The admin gate.

One dependency, used by every route in this module. It is short on purpose:
the whole privilege boundary of the application should fit on a screen.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import ADMIN_TOKEN_TYPE, decode_access_token, oauth2_scheme

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Yönetici kimliği doğrulanamadı.",
    headers={"WWW-Authenticate": "Bearer"},
)


def require_admin(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """Resolve the administrator behind the bearer token, or refuse.

    `typ` is read WITHOUT a default, unlike `get_current_user`, which treats a
    missing claim as an access token so that sessions minted before the claim
    existed keep working. Extending that courtesy here would mean any such
    token is also an admin token -- the one place where being generous about
    an absent claim hands out privilege.
    """
    from .models import AdminUser

    payload = decode_access_token(token)
    username: Optional[str] = payload.get("sub") if payload else None
    if not username:
        raise CREDENTIALS_ERROR

    if payload.get("typ") != ADMIN_TOKEN_TYPE:
        raise CREDENTIALS_ERROR

    administrator = (
        db.query(AdminUser).filter(AdminUser.username == username).first()
    )
    if administrator is None or not administrator.is_active:
        raise CREDENTIALS_ERROR
    return administrator
