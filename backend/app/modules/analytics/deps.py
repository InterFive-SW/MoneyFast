"""Request-level guards for the analytics module."""

import os
from typing import Optional

from fastapi import Header, HTTPException, Query

from app.modules.risk import returns as risk_returns


def lookback_param(lookback: str = Query("1Y")) -> str:
    """The measurement window, normalised to its canonical casing.

    The Analiz screen has ONE period selector driving both this endpoint and
    `/risk/profile`, so both have to accept the same values and mean the same
    thing by them. The set itself is not restated here -- it is read from
    `risk_returns.LOOKBACK_DAYS`, the table the window arithmetic already uses,
    so a window added there is accepted here without anyone remembering to.

    This duplicates the shape of `risk/deps.py:lookback_param`. Only the HTTP
    plumbing is duplicated, not the knowledge; one copy in `core/` would be
    better and is a team decision, and importing another module's router-layer
    helper would build exactly the cross-module dependency the module rules
    exist to prevent.
    """
    upper = (lookback or "1Y").upper()
    if upper not in risk_returns.LOOKBACK_DAYS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"lookback {lookback!r} geçersiz; beklenen: "
                + ", ".join(risk_returns.LOOKBACK_DAYS)
            ),
        )
    return upper


def require_service_token(
    authorization: Optional[str] = Header(default=None),
) -> None:
    """Guard for `GET /report/{user_id}`, which names its subject in the path.

    The report carries positions, cash balance, salary and rent in one
    document -- the sum of surfaces that are each guarded separately. Without
    this, one unauthenticated request would hand over more than any of them.

    An unset BACKEND_API_KEY refuses rather than waves requests through.

    This is the fourth verbatim copy (market/router.py, risk/deps.py,
    investment/deps.py). The honest fix is one copy in `core/`, which is a
    shared file and therefore a team decision; importing another module's
    helper would build exactly the cross-module dependency the module rules
    exist to prevent. Flagged, not taken.
    """
    expected = os.getenv("BACKEND_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Service endpoint is not configured (BACKEND_API_KEY unset).",
        )
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid service credentials.")
