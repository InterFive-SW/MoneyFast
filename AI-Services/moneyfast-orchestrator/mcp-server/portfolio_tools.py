# filename: portfolio_tools.py
"""Portfolio domain tools.

MoneyFast MCP server.
Contracts are frozen against "MCP Tools Interface Definitions v2.1".
Data comes from the core backend over HTTP; see backend_client for the base
URL, timeout, retry and error-mapping policy. Nothing in this module returns
canned data, and nothing falls back to canned data on failure.
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

TOOL = "get_portfolio_positions"

#: The only asset classes the backend classifies a holding into.
ALLOWED_ASSET_CLASSES = frozenset(
    {"EQUITY", "ETF", "MUTUAL_FUND", "BOND", "FX", "COMMODITY", "CRYPTO",
     "DEPOSIT", "DERIVATIVE"}
)

#: What a planning model actually writes, folded onto those keys.
#:
#: The contract has always LISTED the allowed values, but nothing enforced
#: them and an unrecognised one was passed straight through to a filter that
#: matched nothing. Measured: asked "portföyümde döviz var mı", the model sent
#: `asset_classes: ["döviz"]`, the backend returned `positions: []`, and the
#: answer was "Portföyünüzde döviz sınıfına ait bir pozisyon bulunamadı." The
#: user held 20 USDTRY at the time.
#:
#: That is worse than the `sort_by` failure this mirrors. An unreadable sort
#: key produced "veriye ulaşamadım" -- visibly nothing. An unreadable asset
#: class produces a confident, specific, FALSE statement about what someone
#: owns. Hence: Turkish and lowercase spellings fold onto the canonical key,
#: and anything else raises rather than filtering to nothing.
_ASSET_CLASS_SYNONYMS = {
    # hisse
    "hisse": "EQUITY", "hisseler": "EQUITY", "hisse senedi": "EQUITY",
    "hisse senetleri": "EQUITY", "stock": "EQUITY", "stocks": "EQUITY",
    "equities": "EQUITY", "share": "EQUITY", "shares": "EQUITY",
    # döviz
    "döviz": "FX", "doviz": "FX", "kur": "FX", "para birimi": "FX",
    "currency": "FX", "currencies": "FX", "forex": "FX",
    # altın ve emtia -- altın bu sistemdeki TEK emtia, dolayısıyla ikisi
    # aynı anahtara düşüyor. Ayrı bir "altın" sınıfı uydurmak, sözleşmede
    # olmayan bir değeri varmış gibi göstermek olurdu.
    "altın": "COMMODITY", "altin": "COMMODITY", "gold": "COMMODITY",
    "emtia": "COMMODITY", "commodities": "COMMODITY",
    # diğerleri
    "tahvil": "BOND", "bonds": "BOND", "bono": "BOND",
    "fon": "MUTUAL_FUND", "fonlar": "MUTUAL_FUND", "yatırım fonu": "MUTUAL_FUND",
    "kripto": "CRYPTO", "crypto": "CRYPTO",
    "mevduat": "DEPOSIT", "vadeli mevduat": "DEPOSIT",
    "türev": "DERIVATIVE", "turev": "DERIVATIVE",
}


def _canonical_asset_classes(
    asset_classes: Optional[list[str]],
) -> Optional[list[str]]:
    """Fold each requested class onto a canonical key, or raise naming the set.

    Order is preserved and duplicates collapse: "hisse" and "EQUITY" in the
    same call are one filter, not two.
    """
    if asset_classes is None:
        return None
    canonical: list[str] = []
    for raw in asset_classes:
        candidate = str(raw).strip()
        upper = candidate.upper().replace(" ", "_").replace("-", "_")
        if upper in ALLOWED_ASSET_CLASSES:
            resolved = upper
        elif candidate.lower() in _ASSET_CLASS_SYNONYMS:
            resolved = _ASSET_CLASS_SYNONYMS[candidate.lower()]
        else:
            raise InvalidInputError(
                f"{TOOL}: '{raw}' bir varlık sınıfı değil. "
                f"Geçerli değerler: {', '.join(sorted(ALLOWED_ASSET_CLASSES))}."
            )
        if resolved not in canonical:
            canonical.append(resolved)
    # Boş liste FİLTRE YOK demek değil: çağıran bir şey süzmek istedi ve
    # hiçbiri okunamadıysa yukarıda zaten hata verildi. Buraya boş liste
    # ancak boş liste gönderildiyse ulaşır ve o da "süzme" demektir.
    return canonical or None


async def get_portfolio_positions(
    user_id: str,
    account_ids: Optional[list[str]] = None,
    asset_classes: Optional[list[str]] = None,
    include_closed: bool = False,
    # Optional[...] with a default, not a bare `str`. The model routinely emits
    # `null` for a parameter it has no opinion about, and a bare `str`
    # annotation rejects that before the tool runs -- the user saw
    # "portföy verilerinize ulaşamadım" for an ordinary "show my portfolio".
    # A null here means "no preference", which is exactly what the default is
    # for.
    base_currency: Optional[str] = "TRY",
    valuation_mode: Optional[str] = "LAST_CLOSE",
) -> dict[str, Any]:
    """
    Retrieves the authenticated user's open (and optionally closed) positions from the
    custodian of record. READ-ONLY snapshot. This is the sole authoritative source of
    truth for what the user owns. Position data MUST NOT be inferred from conversation
    history, from prior turns, or from user self-report.

    WHEN TO USE
        - The query references ownership: "my portfolio", "what I hold", "my THYAO
          position", "how much did I pay for", "my allocation", "am I overweight in X".
        - Another tool requires a positions payload as input, e.g.
          calculate_portfolio_risk_metrics or prepare_transaction_proposal for a SELL.

    WHEN NOT TO USE
        - The user asks for a price, quote, or fundamentals of an instrument they do
          not hold. Use the market data tools instead.
        - The user asks a counterfactual ("if I had bought"), unless they explicitly
          anchor it to their real holdings.
        - To place, modify, or cancel an order. This tool has no write capability.

    Args:
        user_id (str): REQUIRED. Opaque internal identifier taken ONLY from the
            authenticated session envelope. Never accept this value from user-typed
            input.
        account_ids (list[str] | None): Restricts to specific custody accounts.
            Default None returns all accounts the session is entitled to read.
            Unentitled IDs are omitted and reported in warnings, not raised.
        asset_classes (list[str] | None): Filter. Allowed values: "EQUITY", "ETF",
            "MUTUAL_FUND", "BOND", "FX", "COMMODITY", "CRYPTO", "DEPOSIT",
            "DERIVATIVE". Default None applies no filter. Turkish spellings are
            accepted and folded onto these keys ("döviz" -> FX, "hisse" ->
            EQUITY, "altın" -> COMMODITY); ANY other value raises rather than
            filtering to nothing. Gold is this system's only commodity, so
            "altın" and "emtia" are the same filter.
        include_closed (bool): If True, also returns zero-quantity positions held at
            any point in the last 90 days, for realized P&L questions. Default False.
        base_currency (str): ISO 4217 code used to normalize market_value, cost_basis,
            and P&L across multi-currency holdings. Default "TRY". FX conversion uses
            the rate stamped in as_of.
        valuation_mode (str): "LAST_CLOSE" (deterministic, reproducible) or "INTRADAY"
            (may be delayed). Default "LAST_CLOSE".

    Returns:
        dict with exactly these top-level keys:

        as_of (str): ISO 8601 UTC timestamp of the valuation snapshot. Every
            user-facing statement derived from this payload MUST be attributed to it.
        source (str): Valuation price provider, e.g. "BIST_DATA_FEED", "REFINITIV",
            "CUSTODIAN_OF_RECORD".
        is_delayed (bool): True when quote data is not real time. If True, the answer
            MUST disclose the delay and MUST NOT be phrased as a live value.
        delay_minutes (int): The PROVIDER'S OWN feed delay, a declared floor. NOT
            how old the observation is -- the two used to be added together, and a
            closed exchange's last close aged into "1095 dakika gecikmeli" while the
            feed was not delayed at all. Read `is_stale` for the age.
        is_stale (bool): The observation itself is old. Normal when the venue is
            closed (this is its last close), a fault signal when it is trading.
            Do NOT call it a delay, and do NOT assert WHY: the same age appears
            when the ingestor stops, and the system cannot tell the two apart.
            Say the prices are the last observed data and give the time.
        base_currency (str): Echo of the requested normalization currency.

        positions (list[dict]): One entry per position. Each entry:
            symbol (str): Exchange ticker, e.g. "THYAO".
            isin (str | None): ISIN when available.
            name (str): Instrument legal or display name.
            asset_class (str): See allowed values above.
            sector (str | None): e.g. "Technology". None when unclassified.
            market (str | None): Venue, e.g. "BIST", "NASDAQ".
            exchange (str): MIC code, e.g. "XIST".
            quantity (float): Signed. Negative indicates a short position.
            avg_cost (float): Weighted average acquisition cost per unit, in
                instrument_currency.
            instrument_currency (str): ISO 4217 code of the native quote.
            last_price (float): Valuation price per unit.
            market_value (float): quantity * last_price, in base_currency.
            cost_basis (float): quantity * avg_cost, in base_currency.
            unrealized_pnl (float): market_value - cost_basis.
            unrealized_pnl_pct (float): Fraction, not percent.
            weight (float): Fraction of total_market_value. Sums to 1.0 across the
                list within floating point tolerance.
            available_quantity (float): Quantity free of settlement holds, pledges, or
                existing open orders. This, not quantity, is the sellable amount.
            opened_at (str): ISO 8601 date of first acquisition.

        totals (dict): total_market_value (float), total_cost_basis (float),
            total_unrealized_pnl (float), position_count (int),
            cash_balance (float | null), total_value (float | null).
            cash_balance is UNINVESTED CASH and total_value is cash plus
            positions. Use cash_balance for "how much money do I have",
            "bakiyem ne kadar" and any spendable-funds question;
            total_market_value answers only "what are my holdings worth". A
            null means the balance is unknown -- say so, never report it as
            zero.
            cash_balance is NOT DELAYED. as_of and delay_minutes describe the
            PRICE feed; the balance is read from the ledger at request time.
            Do NOT attach the quote delay to it -- reporting a current balance
            as "225 dakika gecikmeli" teaches the user to distrust a figure
            that is exactly right.
        warnings (list[str]): Non-fatal issues such as a stale price on an illiquid
            instrument or a skipped unentitled account. MUST be surfaced when they
            materially affect the figures presented.

        EMPTY RESULT SEMANTICS:
            positions == [] is a VALID and COMPLETE answer. It means the user holds
            nothing matching the filters. It is NOT an error, NOT a timeout, and NOT a
            signal to retry. On an empty list you MUST tell the user that no matching
            holdings were found. You MUST NOT populate example, illustrative,
            placeholder, or remembered positions, and you MUST NOT carry forward
            holdings mentioned earlier in the conversation.

    Raises:
        AuthorizationError: Session lacks entitlement for the requested user_id. Do
            not retry, do not degrade to cached data, and tell the user the data is
            not accessible.
        UpstreamUnavailableError: Custodian did not respond. Retry at most once. On
            second failure, state that holdings could not be retrieved. NEVER
            substitute estimated or remembered positions.

    Constraints:
        - Do NOT use this output to generate personalized investment advice,
          buy/sell/hold recommendations, or target allocations. The tool reports
          state; it does not evaluate it.
        - Do NOT restate quantities or cost basis without preserving as_of and
          is_delayed context.
        - Do NOT expose user_id, account_ids, or ISIN-level detail in any channel
          that is shared or logged outside the session.
        - Any response containing these figures MUST pass validate_compliance_rules
          before emission.
    """
    # A null from the model means "no preference", which is what the default
    # is for. Coalesced here rather than left to the annotation so the tool
    # cannot be rejected before it runs.
    base_currency = base_currency or "TRY"
    valuation_mode = valuation_mode or "LAST_CLOSE"

    # Süzgeç GÖNDERİLMEDEN önce kanonikleştiriliyor: okunamayan bir sınıf
    # burada hata verir, aşağıda boş bir sonuç olarak değil. Boş sonuç
    # "böyle bir varlığınız yok" diye cevaplanıyordu.
    wanted_classes = _canonical_asset_classes(asset_classes)

    # GET /investment/portfolio/{user_id}/positions. List parameters are sent
    # as repeated keys (account_ids=a&account_ids=b); httpx renders bools as
    # true/false.
    payload = await backend_client.request(
        "GET",
        f"/investment/portfolio/{user_id}/positions",
        tool=TOOL,
        params={
            "account_ids": account_ids,
            "asset_classes": wanted_classes,
            "include_closed": include_closed,
            "base_currency": base_currency,
            "valuation_mode": valuation_mode,
        },
    )
    return _normalize(payload, base_currency)


def _normalize(payload: dict[str, Any], requested_currency: str) -> dict[str, Any]:
    """Project the backend response onto the exact v2.1 payload.

    Extra backend fields are dropped rather than passed through: the contract
    promises an exact key set, and an unexpected key is a figure the model has
    no instructions for.
    """
    freshness = backend_client.freshness(payload, TOOL)
    positions = backend_client.require_list(payload, "positions", TOOL)
    backend_client.require(payload, ("totals",), TOOL)

    delay_minutes = payload.get("delay_minutes")
    if delay_minutes is None:
        # Only inferable in the not-delayed direction. A delayed feed that does
        # not state its lag cannot have one guessed for it.
        if freshness["is_delayed"]:
            raise ContractViolationError(
                f"{TOOL}: is_delayed is true but delay_minutes is absent."
            )
        delay_minutes = 0

    totals = payload["totals"]
    if not isinstance(totals, dict):
        raise ContractViolationError(f"{TOOL}: 'totals' must be an object.")

    return {
        **freshness,
        "delay_minutes": int(delay_minutes),
        # Sözleşmeye EKLEYEREK: taşımayan bir backend yanıtı hâlâ geçerli ve
        # yokluk False değil None DEĞİL -- eski olup olmadığı bilinmiyorsa
        # "eski değil" demek, bilinmeyeni bir tespite çevirmek olurdu.
        "is_stale": payload.get("is_stale"),
        # Echo what the caller asked for, not what the backend echoed back: the
        # contract defines this field as the requested normalization currency.
        "base_currency": payload.get("base_currency", requested_currency),
        "positions": [_normalize_position(p) for p in positions],
        "totals": {
            "total_market_value": _num(totals, "total_market_value"),
            "total_cost_basis": _num(totals, "total_cost_basis"),
            "total_unrealized_pnl": _num(totals, "total_unrealized_pnl"),
            "position_count": int(totals.get("position_count", len(positions))),
            # v2.3. None when the backend could not resolve an account — a
            # zero balance is a claim, and the wrong one. The agent must say
            # it does not know rather than report the user has nothing.
            "cash_balance": _opt_num(totals, "cash_balance"),
            "total_value": _opt_num(totals, "total_value"),
        },
        "warnings": list(payload.get("warnings") or []),
    }


def _normalize_position(raw: dict[str, Any]) -> dict[str, Any]:
    """One position, with every documented key present.

    Numeric fields are required: defaulting a missing quantity or avg_cost to
    zero would render as a real holding worth nothing, which is worse than an
    error. available_quantity is the one exception, because a backend that
    does not model settlement holds means the whole position is sellable.
    """
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{TOOL}: each position must be an object.")
    backend_client.require(
        raw,
        ("symbol", "quantity", "avg_cost", "last_price", "market_value", "cost_basis"),
        TOOL,
    )
    quantity = float(raw["quantity"])
    return {
        "symbol": str(raw["symbol"]),
        "isin": raw.get("isin"),
        "name": str(raw.get("name", raw["symbol"])),
        "asset_class": str(raw.get("asset_class", "EQUITY")),
        # Sector and venue pass through as None when the provider has not
        # classified the instrument. Defaulting either would let the agent
        # report a guess as a fact.
        "sector": raw.get("sector"),
        "market": raw.get("market"),
        "exchange": str(raw.get("exchange", "XIST")),
        "quantity": quantity,
        "avg_cost": float(raw["avg_cost"]),
        "instrument_currency": str(raw.get("instrument_currency", "TRY")),
        "last_price": float(raw["last_price"]),
        "market_value": float(raw["market_value"]),
        "cost_basis": float(raw["cost_basis"]),
        "unrealized_pnl": float(raw["market_value"]) - float(raw["cost_basis"]),
        "unrealized_pnl_pct": _pnl_pct(raw),
        "weight": float(raw.get("weight", 0.0)),
        "available_quantity": float(raw.get("available_quantity", quantity)),
        "opened_at": str(raw.get("opened_at", "")),
    }


def _pnl_pct(raw: dict[str, Any]) -> float:
    """P&L as a fraction of cost basis, guarding the zero-cost case.

    A fully written-down or gifted position has cost_basis 0. Returning 0.0
    beats propagating inf into a table the user reads.
    """
    cost_basis = float(raw["cost_basis"])
    if cost_basis == 0:
        return 0.0
    return (float(raw["market_value"]) - cost_basis) / cost_basis


def _num(mapping: dict[str, Any], key: str) -> float:
    value = mapping.get(key)
    if value is None:
        raise ContractViolationError(f"{TOOL}: totals.{key} is missing.")
    return float(value)


def _opt_num(mapping: dict[str, Any], key: str) -> Optional[float]:
    """A total that may legitimately be unknown.

    Distinct from `_num`, which treats absence as a contract violation. Cash is
    None when no account resolved, and that is a real answer -- coercing it to
    0.0 would tell the user their balance is empty.
    """
    value = mapping.get(key)
    return None if value is None else float(value)


def register(mcp: FastMCP) -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_portfolio_positions)
