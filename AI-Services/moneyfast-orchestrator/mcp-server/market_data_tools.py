# filename: market_data_tools.py
"""Market data domain tools.

MoneyFast MCP server. Added in contract v2.2; the six v2.1 tools are
unchanged.

Why this exists: v2.1 could read a user's holdings, retrieve documents,
measure risk, stage a transaction, screen a draft and route a turn — and could
not answer "THYAO kaç lira?" for an instrument the user does not own. The
system was collecting live prices the assistant had no way to see.

Data comes from the core backend over HTTP; see backend_client for the base
URL, timeout, retry and error-mapping policy. Nothing here returns canned data,
and nothing falls back to canned data on failure.
"""

# from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

import backend_client
from backend_client import (
    AuthorizationError,
    ContractViolationError,
    InvalidInputError,
    UpstreamUnavailableError,
)

TOOL = "get_market_data"
MIN_TOP_K = 1
MAX_TOP_K = 50

#: Applied when the caller passes no preference (or an explicit null).
DEFAULT_TOP_K = 20

#: Filter keys the backend understands. An unknown key is rejected rather than
#: dropped: the contract tells the model a filter was applied, and silently
#: ignoring one turns "no matches" into a false statement about the market.
ALLOWED_FILTERS = frozenset({"sector", "market", "max_pe", "min_pe", "max_pb"})

#: Canonical sort keys. `change_percent` ranks the biggest risers first and
#: `change_percent_asc` the biggest fallers: without the ascending variant
#: "en çok düşenler" was unanswerable, and the descending key silently served
#: gainers for a losers question.
ALLOWED_SORTS = frozenset(
    {"symbol", "change_percent", "change_percent_asc", "market_cap", "pe_ratio"}
)

#: Shapes a planning model actually emits, folded onto the canonical keys.
#:
#: These are phrasings of the SAME intent, not guesses at a different one: a
#: model asked for top gainers writes `gainers`, `top_gainers` or
#: `change_percent_desc` about as often as it writes `change_percent`, and
#: rejecting those made the answer depend on which synonym it happened to pick.
#: Anything outside this table still raises — an argument we cannot read is not
#: quietly reinterpreted.
_SORT_SYNONYMS = {
    "gainers": "change_percent",
    "top_gainers": "change_percent",
    "change_percent_desc": "change_percent",
    "-change_percent": "change_percent",
    "change_percent desc": "change_percent",
    "losers": "change_percent_asc",
    "top_losers": "change_percent_asc",
    "change_percent asc": "change_percent_asc",
    "market_cap_desc": "market_cap",
    "-market_cap": "market_cap",
    "pe": "pe_ratio",
    "pe_ratio_asc": "pe_ratio",
}


def _canonical_sort(sort_by: Optional[str]) -> Optional[str]:
    """Fold a model's phrasing onto a canonical key, or raise naming the set."""
    if sort_by is None:
        return None
    candidate = str(sort_by).strip().lower().replace("-", "_").replace("  ", " ")
    if candidate in ALLOWED_SORTS:
        return candidate
    # Look the raw form up too, so "-change_percent" is found before the dash
    # is normalised away.
    for key in (str(sort_by).strip().lower(), candidate, candidate.replace("_", " ")):
        if key in _SORT_SYNONYMS:
            return _SORT_SYNONYMS[key]
    raise InvalidInputError(
        f"{TOOL}: unrecognised sort_by {sort_by!r}; allowed: {', '.join(sorted(ALLOWED_SORTS))}."
    )


async def get_market_data(
    symbols: Optional[list[str]] = None,
    filters: Optional[dict[str, Any]] = None,
    # Optional rather than a plain int with a default: an LLM routinely names
    # every parameter and passes `top_k: null` for "I have no preference".
    # A bare `int = 20` rejects that as a validation error, and the agent then
    # tells the user it could not reach the data — which is what happened to
    # "THYAO kaç lira?".
    top_k: Optional[int] = None,
    # Süzgeçlerin YANLIŞ YERE yazılmış hâli. Model bunları düzenli olarak üst
    # seviyede gönderiyor (`{"sector": "bankacilik", "top_k": 20}`) ve
    # imzada yoklarken sessizce DÜŞÜYORLARDI: ölçüldü, "bankacılık
    # sektöründe hangi hisseler var" sorusuna evrenin alfabetik ilk yirmisi
    # (A, AAP, AAPL, ABBV, ABNB) süzülmüş bir liste gibi döndü.
    #
    # Kabul edilip `filters`a taşınıyorlar. `filters` içindeki tanınmayan bir
    # anahtar hâlâ REDDEDİLİYOR ve gerekçe aynı: sessizce yok sayılan bir
    # süzgeç, "eşleşme yok"u yanlış bir iddiaya çevirir. Burada niyet açık
    # olduğu için düzeltmek reddetmekten iyi -- `_SORT_SYNONYMS` ile aynı
    # ders.
    sector: Optional[str] = None,
    market: Optional[str] = None,
    max_pe: Optional[float] = None,
    min_pe: Optional[float] = None,
    max_pb: Optional[float] = None,
    sort_by: Optional[str] = None,
) -> dict[str, Any]:
    """
    Retrieves current prices and valuation fundamentals for named instruments, or
    screens the instrument universe against explicit numeric criteria. READ-ONLY. This
    is the sole authoritative source for the price of an instrument the user does not
    hold, and for any valuation ratio.

    WHEN TO USE
        - The query asks the price, daily move, or 52-week range of a named instrument:
          "THYAO kaç lira", "ASELS bugün nasıl", "dolar kaç TL".
        - The query asks for a screen against stated objective criteria: "F/K'sı 10'un
          altındaki hisseler", "bankacılık sektöründeki şirketler", "piyasa değeri en
          büyük 5 şirket".
        - A valuation ratio is needed for any instrument, held or not.

    WHEN NOT TO USE
        - The user asks what they own, or the value of their own position. Use
          get_portfolio_positions; this tool has no access to holdings.
        - The user asks WHY something moved, or what analysts think. Those are
          qualitative and belong to rag_semantic_market_search.
        - The user asks for historical volatility, drawdown or beta. Those are
          computed by calculate_portfolio_risk_metrics from a return series; a
          current price cannot produce them.
        - To place, modify or price an order. Use prepare_transaction_proposal.

    Args:
        symbols (list[str] | None): Instruments to fetch, e.g. ["THYAO", "ASELS"].
            Written as the user wrote them; the backend resolves case, the ".IS"
            provider suffix, and company names. Mutually informative with filters:
            supplying both narrows the named set. Default None means "screen".
        filters (dict | None): Screening criteria applied before ranking. Recognized
            keys ONLY:
                sector (str): e.g. "Industrials". Case-insensitive.
                market (str): "BIST", "NASDAQ", "FX".
                max_pe (float), min_pe (float): trailing P/E bounds.
                max_pb (float): price-to-book upper bound.
            An unrecognized key raises rather than being ignored.
            IMPORTANT: a fundamental filter EXCLUDES instruments whose value is
            unknown. "P/E below 10" never silently means "P/E below 10, or missing".
        top_k (int): Maximum instruments returned. Range 1 to 50. Default 20.
        sort_by (str | None): One of "symbol", "change_percent", "market_cap",
            "pe_ratio". Default "symbol". Sorting is a presentation choice over
            objective values; it is NOT a ranking by investment merit.

    Returns:
        dict with exactly these top-level keys:

        as_of (str): ISO 8601 UTC timestamp of the OLDEST quote in the result set. A
            payload is only as current as its least current figure, so every statement
            derived from it MUST be attributed to this instant.
        source (str): Price provider, e.g. "YFINANCE_DELAYED".
        is_delayed (bool): True when quotes are not real time. If True, the answer MUST
            disclose the delay and MUST NOT be phrased as a live price.
        delay_minutes (int): Quote delay in minutes. 0 when is_delayed is False.

        instruments (list[dict]): One entry per instrument. Each entry:
            symbol (str), name (str), market (str | None), currency (str).
            price (float): Last traded or last close.
            change (float | None), change_percent (float | None): Versus previous
                close. None means UNKNOWN, not unchanged.
            volume (int | None): Last session's traded volume, in shares.
            pe_ratio, pb_ratio, dividend_yield, market_cap, sector,
            week52_high, week52_low: All nullable. **null means the provider does
                not publish it.** Report it as "veri yok". NEVER render a null as
                0, never omit the instrument to hide the gap, and never infer the
                value from a peer.

        filters_echo (dict): The filters actually applied.
        warnings (list[str]): Symbols that could not be resolved, and any filter
            that excluded instruments for missing data.

        EMPTY RESULT SEMANTICS:
            instruments == [] is a VALID and COMPLETE answer. It means no instrument
            in the universe matched. You MUST say so. You MUST NOT widen the filters
            silently, MUST NOT substitute instruments that fail the criteria, and MUST
            NOT present remembered or illustrative tickers as matches.

    Raises:
        InvalidInputError: Unrecognized filter key or sort field. Correct and retry
            once; do not drop the filter.
        UpstreamUnavailableError: Market data service unreachable. State that prices
            could not be retrieved. NEVER answer with a remembered price — a stale
            price presented as current is indistinguishable from a wrong one.

    Constraints:
        - Do NOT use this output to recommend, rank by attractiveness, or call an
          instrument cheap, expensive, undervalued or overvalued. Reporting that a
          P/E is 8.2 is permitted; concluding the stock is cheap is not.
        - A screen is a filter, not a suggestion. Presenting results MUST include the
          criteria that produced them and the mandatory non-advisory disclosure.
        - Do NOT compare a ratio against an unstated "good" threshold.
        - NEVER state a price without its as_of, and never as live when is_delayed.
        - Any response containing these figures MUST pass validate_compliance_rules
          before emission.
    """
    sort_by = _canonical_sort(sort_by)

    filters = dict(filters or {})
    # Üst seviyeye yazılmış süzgeçler yerlerine taşınıyor. `filters` içinde
    # zaten varsa oradaki kazanıyor: iki yere birden yazılmışsa, niyeti
    # doğru yerdeki söylüyor.
    for key, value in (
        ("sector", sector), ("market", market),
        ("max_pe", max_pe), ("min_pe", min_pe), ("max_pb", max_pb),
    ):
        if value is not None:
            filters.setdefault(key, value)
    unknown = sorted(set(filters) - ALLOWED_FILTERS)
    if unknown:
        # Rejected rather than dropped: the model believes the filter applied,
        # and a silently ignored one turns "no matches" into a false claim.
        raise InvalidInputError(
            f"{TOOL}: unrecognised filter key(s): {', '.join(unknown)}."
        )

    params: dict[str, Any] = {
        "limit": max(MIN_TOP_K, min(MAX_TOP_K, DEFAULT_TOP_K if top_k is None else top_k)),
        "sort_by": sort_by,
    }
    if symbols:
        params["symbols"] = symbols
    params.update({key: value for key, value in filters.items() if value is not None})

    payload = await backend_client.request(
        "GET", "/market/instruments", tool=TOOL, params=params
    )
    return _normalize(payload, symbols or [], filters)


def _normalize(
    payload: Any, requested_symbols: list[str], filters: dict[str, Any]
) -> dict[str, Any]:
    """Project the backend response onto the exact v2.2 payload.

    Freshness is derived here from the quotes themselves rather than trusted:
    `as_of` is the OLDEST timestamp in the set, because a payload is only as
    current as its least current figure. Taking the newest would let one fresh
    instrument vouch for twenty stale ones.
    """
    rows = backend_client.require_list(payload, "instruments", TOOL)
    instruments = [_normalize_instrument(item) for item in rows]

    stamps = [item["as_of"] for item in instruments if item["as_of"]]
    as_of = min(stamps) if stamps else ""
    # Our own staleness plus the provider's declared lag. Reporting only the
    # former would present a price fetched one second ago as real time, which
    # a delayed feed never is.
    delay_minutes = (_delay_minutes(as_of) + PROVIDER_DELAY_FLOOR_MINUTES) if instruments else 0

    warnings: list[str] = []
    returned = {item["symbol"].upper() for item in instruments}

    # Which queries actually failed is the BACKEND's answer, not something to
    # infer here. Diffing what was typed against what came back marks "THY" as
    # missing when THYAO is sitting in the payload -- the resolver did its job
    # and the user would still be told the stock was not found. Only fall back
    # to the diff for a backend that predates the field.
    unresolved_field = (payload.get("unresolved") if isinstance(payload, dict) else None)
    if unresolved_field is not None:
        missing = [
            str(item.get("query", "")) for item in unresolved_field
            if isinstance(item, dict) and item.get("query")
        ]
    else:
        missing = [
            symbol for symbol in requested_symbols
            if symbol.upper().replace(".IS", "") not in returned
        ]
    # The backend now says what a failed query might have meant. Prefer that
    # over the bare "not found": "koz" matching KOZAL and KOZAA is a question
    # the user can answer in one word, not a dead end.
    suggested = {
        str(item.get("query", "")).upper(): [str(c) for c in (item.get("candidates") or [])]
        for item in (unresolved_field or [])
        if isinstance(item, dict)
    }
    for symbol in sorted(missing):
        candidates = suggested.get(symbol.upper())
        if candidates:
            warnings.append(
                f"«{symbol}» için tam eşleşme yok. Bunlardan biri mi: "
                + ", ".join(candidates) + "?"
            )
    plain = [s for s in sorted(missing) if not suggested.get(s.upper())]
    if plain:
        warnings.append(
            "Şu semboller bulunamadı veya fiyatı yok: " + ", ".join(plain)
        )
    if any(key in filters for key in ("max_pe", "min_pe", "max_pb")):
        warnings.append(
            "Temel oran filtresi uygulandı; ilgili oranı bilinmeyen enstrümanlar "
            "sonuçlara dahil edilmedi."
        )

    return {
        "as_of": as_of,
        "source": "YFINANCE_DELAYED",
        # Any non-zero lag is disclosed. The provider's BIST data is delayed by
        # design, so claiming otherwise would be false in the ordinary case.
        "is_delayed": delay_minutes > 0,
        "delay_minutes": delay_minutes,
        "instruments": instruments,
        "filters_echo": dict(filters),
        "warnings": warnings,
    }


def _normalize_instrument(raw: Any) -> dict[str, Any]:
    """One instrument, with every documented key present.

    symbol and price are required: an instrument without a price is not a
    screening result, it is a gap, and rendering it in a valuation table
    invites the reader to treat the blank as a number.

    Every fundamental passes through as None when absent. Coalescing to zero
    here would put a company with no published earnings at the top of a
    "lowest P/E" list.
    """
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{TOOL}: each instrument must be an object.")
    backend_client.require(raw, ("symbol", "price", "market_timestamp"), TOOL)

    return {
        "symbol": str(raw["symbol"]),
        "name": str(raw.get("name") or raw["symbol"]),
        "market": raw.get("market"),
        "currency": str(raw.get("currency") or "TRY"),
        "price": float(raw["price"]),
        "change": _opt_float(raw.get("change")),
        "change_percent": _opt_float(raw.get("change_percent")),
        # Daily traded volume. The backend stored it on every quote and
        # exposed it nowhere, so a screening table's turnover column was
        # structurally empty rather than occasionally unknown.
        "volume": int(raw["volume"]) if raw.get("volume") is not None else None,
        "pe_ratio": _opt_float(raw.get("pe_ratio")),
        "pb_ratio": _opt_float(raw.get("pb_ratio")),
        "market_cap": int(raw["market_cap"]) if raw.get("market_cap") is not None else None,
        "dividend_yield": _opt_float(raw.get("dividend_yield")),
        "sector": raw.get("sector"),
        "week52_high": _opt_float(raw.get("week52_high")),
        "week52_low": _opt_float(raw.get("week52_low")),
        # Observation time, not the bar's own stamp. Daily bars are stamped at
        # the session open, so a price fetched at 15:30 carries a 00:00 stamp;
        # measuring staleness from it reported a current price as 748 minutes
        # old. The provider's own lag is declared separately as a floor.
        "as_of": str(raw.get("received_at") or raw["market_timestamp"]),
    }


def _opt_float(value: Any) -> Optional[float]:
    """None stays None. This is the whole point: a missing ratio is unknown,
    not zero."""
    return None if value is None else float(value)


#: The provider's own feed delay for BIST quotes, in minutes. Declared as a
#: floor rather than pretended away: even a price fetched a second ago reached
#: us late, and the contract forbids presenting a delayed quote as live.
PROVIDER_DELAY_FLOOR_MINUTES = 15


def _delay_minutes(as_of: str) -> int:
    from datetime import datetime, timezone

    if not as_of:
        return 0
    try:
        stamp = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - stamp).total_seconds() // 60))


def register(mcp: FastMCP) -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_market_data)
