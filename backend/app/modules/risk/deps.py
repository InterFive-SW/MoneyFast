"""Request-level guards for the risk module.

The service-token guard used to live here as a verbatim copy. It moved to
`core/deps.py`: it was duplicated across four modules and knows nothing about
risk, which is exactly what belongs in a shared file.

What is left DOES know something about this module -- the window parameter
validates against `LOOKBACKS`, this module's own set.
"""

from fastapi import HTTPException, Query

from .schemas import LOOKBACKS




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
