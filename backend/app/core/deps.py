"""Shared request dependencies.

Two things live here, and both are here rather than in a module because more
than one module needs them: resolving the authenticated user from the bearer
token, and the guard for the service-to-service endpoints.

The AI path needs this specifically. "MCP Tools Interface Definitions v2.1"
says of `user_id`:

    Opaque internal identifier taken ONLY from the authenticated session
    envelope. Never accept this value from user-typed input.

A client-supplied `user_id` in a chat request body would let anyone read
anyone's holdings by editing one JSON field, so the field does not exist in
the request schema at all and the value is derived here instead.
"""

import os
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    ACCESS_TOKEN_TYPE,
    ADMIN_TOKEN_TYPE,
    decode_access_token,
    oauth2_scheme,
)

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

    # A refresh token is valid for days and is only ever meant to buy a new
    # access token. Accepting one here would make a leaked refresh token
    # equivalent to the password for a week. Tokens minted before `typ`
    # existed carry no claim and are treated as access tokens so live
    # sessions are not invalidated by the deploy.
    if payload.get("typ", ACCESS_TOKEN_TYPE) != ACCESS_TOKEN_TYPE:
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

    # An ADMIN token is not a lapsed customer session -- it is a valid
    # credential for the other identity, and falling through to "anonymous"
    # let it read the demo portfolio and drive the chat. Measured: an admin
    # token answered 200 on /investment/positions and on /chat. Refused here,
    # so the graceful path below stays for the case it was written for.
    payload = decode_access_token(token)
    if payload and payload.get("typ") == ADMIN_TOKEN_TYPE:
        raise CREDENTIALS_ERROR

    try:
        return str(get_current_user(token=token, db=db).id)
    except HTTPException:
        # A bad token on an optional path is treated as anonymous rather than
        # rejected, so an expired session degrades to general questions
        # instead of a wall.
        return None


def require_service_token(
    authorization: Optional[str] = Header(default=None),
) -> None:
    """Guard for every endpoint that names its SUBJECT IN THE PATH.

    Session-bound endpoints resolve the user from the bearer token and can
    only ever return the caller's own data. These cannot: the MCP tool server
    calls them on behalf of a user it names, so without a guard anyone who can
    reach the backend could read anyone's holdings, risk profile, cash flow or
    report by guessing a user id. The backend is also the public ingress, so
    "internal network only" is not true of it.

    Measured while three of them were open: an unauthenticated GET returned
    another user's eleven positions and a total market value of 1.083.211,99
    TRY, and two more handed over the symbols they hold.

    An unset BACKEND_API_KEY refuses rather than waves requests through, and
    with 503 rather than 401: nothing is wrong with the caller's credentials,
    the deployment never configured any. An endpoint that quietly became
    public because an env var was missing is the kind of thing nobody notices.

    ONE COPY, HERE. It was duplicated verbatim in four modules -- market,
    risk, investment, analytics -- and banking imported market's, which is
    exactly the cross-module dependency the module rules exist to prevent.
    Each copy carried the same comment saying the honest fix was one copy in
    `core/` and that this was a team decision; the decision was taken.

    `core/` is shared, so what lives here has to be genuinely domain-free:
    this reads one env var and one header and knows nothing about portfolios,
    risk or reports.
    """
    expected = os.getenv("BACKEND_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Service endpoint is not configured (BACKEND_API_KEY unset).",
        )
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid service credentials.")
