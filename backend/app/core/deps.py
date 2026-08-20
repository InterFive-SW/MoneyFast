"""Shared request dependencies.

Only one thing lives here so far, and it is here rather than in `auth/`
because more than one module needs it: resolving the authenticated user from
the bearer token.

The AI path needs this specifically. "MCP Tools Interface Definitions v2.1"
says of `user_id`:

    Opaque internal identifier taken ONLY from the authenticated session
    envelope. Never accept this value from user-typed input.

A client-supplied `user_id` in a chat request body would let anyone read
anyone's holdings by editing one JSON field, so the field does not exist in
the request schema at all and the value is derived here instead.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token, oauth2_scheme

#: The shared `oauth2_scheme` rejects a missing Authorization header with a
#: 401 before the endpoint runs. The chat endpoint wants the opposite: no
#: token means anonymous, not forbidden. Hence a second scheme that returns
#: None instead of raising.
optional_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login", auto_error=False
)

CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """Resolve the `User` row behind the bearer token.

    `create_access_token` puts the TC number in `sub`, so that is the lookup
    key rather than the primary key. An expired or malformed token yields an
    empty payload from `decode_access_token`, which lands in the same 401 as a
    token for a user who no longer exists -- the caller should not be able to
    tell those apart.
    """
    # Imported here rather than at module scope: `core` must not import a
    # module package at load time, or router auto-discovery in main.py starts
    # depending on import order.
    from app.modules.auth.models import User

    payload = decode_access_token(token)
    tc_no: Optional[str] = payload.get("sub") if payload else None
    if not tc_no:
        raise CREDENTIALS_ERROR

    user = db.query(User).filter(User.tc_no == tc_no).first()
    if user is None or not user.is_active:
        raise CREDENTIALS_ERROR
    return user


def get_current_user_id(user=Depends(get_current_user)) -> str:
    """Just the opaque identifier, for callers that need nothing else."""
    return str(user.id)


def get_optional_user_id(
    token: Optional[str] = Depends(optional_oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[str]:
    """Same resolution, but anonymous access is allowed.

    Used by the chat endpoint so an unauthenticated visitor can still ask
    general questions. It returns None rather than a placeholder string: the
    downstream tools treat a missing user_id as "no portfolio to read", which
    is the correct behaviour, whereas a made-up id would be sent to a
    custodian lookup.
    """
    if not token:
        return None
    try:
        return str(get_current_user(token=token, db=db).id)
    except HTTPException:
        # A bad token on an optional path is treated as anonymous rather than
        # rejected, so an expired session degrades to general questions
        # instead of a wall.
        return None
