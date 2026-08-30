"""Request-level guards for the risk module.

Only one thing lives here: the guard for the service-to-service endpoint the
MCP tool server reads. It is separate from `core/deps.py` because that file is
shared and, per CLAUDE.md, is not changed without the team.
"""

import os
from typing import Optional

from fastapi import Header, HTTPException, Query

from .schemas import LOOKBACKS


def require_service_token(
    authorization: Optional[str] = Header(default=None),
) -> None:
    """Guard for `GET /profile/{user_id}`, which names its subject in the path.

    Session-bound endpoints resolve the user from the bearer token and can
    only ever return the caller's own data. This one cannot: the MCP tool
    server calls it on behalf of a user it names, so without a guard anyone
    who can reach the backend could read anyone's risk profile by guessing a
    user id. The backend is also the public ingress, so "internal network
    only" is not true of it.

    An unset BACKEND_API_KEY refuses rather than waves requests through. An
    endpoint that quietly became public because an env var was missing is the
    kind of thing nobody notices.

    This duplicates `market/router.py:require_service_token` verbatim. The
    honest fix is one copy in `core/`, which is a shared file and therefore a
    team decision -- importing a helper out of another module's router would
    build exactly the cross-module dependency the module rules exist to
    prevent, so the duplicate is the smaller of the two costs for now.
    """
    expected = os.getenv("BACKEND_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Service endpoint is not configured (BACKEND_API_KEY unset).",
        )
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid service credentials.")


def lookback_param(lookback: str = Query("1Y")) -> str:
    """The measurement window, normalised to its canonical casing.

    A closed set, because `returns.window_for` falls back to 252 bars for
    anything it does not recognise: before this, `lookback=3Yil` quietly
    returned one year of data under a three-year label.

    Casing is normalised rather than rejected, which is what `RiskRequest`
    already does for the same value in a request body. Held to `Literal`
    instead, this refused the planner's `"1y"` with a 422 -- the model writes
    lowercase, the body accepted it, and only the query string did not. The
    user saw "Verilere ulaşamadım" for a window that was perfectly valid.
    """
    upper = lookback.upper()
    if upper not in LOOKBACKS:
        raise HTTPException(
            status_code=422,
            detail=f"lookback {lookback!r} geçersiz; beklenen: {', '.join(LOOKBACKS)}",
        )
    return upper
