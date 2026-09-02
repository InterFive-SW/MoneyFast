"""Request-level guards for the investment module.

Only one thing lives here: the guard for the service-to-service endpoint the
MCP tool server reads. It is separate from `core/deps.py` because that file is
shared and, per CLAUDE.md, is not changed without the team.
"""

import os
from typing import Optional

from fastapi import Header, HTTPException


def require_service_token(
    authorization: Optional[str] = Header(default=None),
) -> None:
    """Guard for `GET /portfolio/{user_id}/positions`, which names its subject
    in the path.

    Session-bound endpoints resolve the user from the bearer token and can
    only ever return the caller's own data. This one cannot: the MCP tool
    server calls it on behalf of a user it names, so without a guard anyone
    who can reach the backend could read anyone's holdings by guessing a user
    id. The backend is also the public ingress, so "internal network only" is
    not true of it.

    Measured while it was open: an unauthenticated GET returned another user's
    eleven positions and a total market value of 1.083.211,99 TRY. The
    session-scoped `/investment/positions` is unaffected -- it is a different
    endpoint for a different consumer and resolves its user from the token.

    An unset BACKEND_API_KEY refuses rather than waves requests through. An
    endpoint that quietly became public because an env var was missing is the
    kind of thing nobody notices.

    This is now the THIRD verbatim copy, after `market/router.py` and
    `risk/deps.py`. The honest fix is one copy in `core/`, which is a shared
    file and therefore a team decision; importing a helper out of another
    module would build exactly the cross-module dependency the module rules
    exist to prevent. Three copies is the point at which that team decision is
    worth making -- flagged rather than taken here.
    """
    expected = os.getenv("BACKEND_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Service endpoint is not configured (BACKEND_API_KEY unset).",
        )
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid service credentials.")
