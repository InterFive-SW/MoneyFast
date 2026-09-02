"""Koşullu senaryo, stres testi ve pozisyon simülasyonu — üçü de ÖLÇÜM.

Sözleşme v2.13. Bu üç araç tek bir soru ailesini cevaplıyor: *ne olurdu?* --
ve üçünün cevabı da bir tahmin değil, geçmiş verinin aritmetiği.

Ayrım kritik, çünkü ürünün ileriye dönük konuşma sınırı kodda yazılı
(GUA-003): çekinceye bağlanmamış yön iddiası engelleniyor, koşullu ve
çekinceli okuma engellenmiyor. Bu araçlar ikinci türü üretiyor ve cümleyi
BACKEND kuruyor -- modele sayı verip yorumlatmak, aynı ölçümün her turda
biraz farklı anlatılması demekti.

`simulate_position_change` yeni bir yetenek DEĞİL: `/risk/simulate` aylardır
yazılmış ve test edilmişti, hiçbir MCP aracı onu çağırmıyordu. "Şu hisseden
alsam riskim ne olur" sorusunun cevabı vardı ve sohbetten erişilemiyordu.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

import backend_client
from backend_client import ContractViolationError

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

SCENARIO_TOOL = "run_portfolio_scenario"
STRESS_TOOL = "get_portfolio_stress_test"
SIMULATE_TOOL = "simulate_position_change"

#: Ölçülebilir faktörler. Backend'in `scenario.FACTORS`'ıyla AYNI liste;
#: ayrışırlarsa model geçersiz bir faktör üretir ve kullanıcı 422 alır --
#: `market_data_tools.ALLOWED_SORTS` ile `prompts.py` arasında bir kez
#: yaşanmış bir hata bu.
FACTORS = ("USDTRY", "EURTRY", "XU100", "XAUUSD")


async def run_portfolio_scenario(
    user_id: str,
    factor: str,
    shock_pct: float,
    lookback: Optional[str] = None,
) -> dict[str, Any]:
    """
    Measures how the user's portfolio has historically moved with one macro factor, and
    reports what a hypothetical move in that factor would have implied. READ-ONLY.
    This is ARITHMETIC OVER PAST RETURNS, not a forecast: it says nothing about what the
    factor will do, only what the portfolio did when the factor moved.

    WHEN TO USE
        - The user asks a conditional macro question about their holdings: "dolar
          yükselirse portföyüm ne olur", "borsa %10 düşse ne kaybederim", "euro
          çıkarsa etkilenir miyim", "altın portföyümü etkiler mi".

    WHEN NOT TO USE
        - The user asks what the factor WILL do. Nothing in this system forecasts a
          price, and this tool does not either.
        - The user asks about buying or selling something. Use
          simulate_position_change; this tool changes no holding.
        - The user asks what already happened in a bad stretch. Use
          get_portfolio_stress_test — that reports real days, this reports a
          hypothetical.
        - INTEREST RATES. There is no interest-rate series in this system, so rate
          scenarios cannot be measured. Say that plainly; do NOT substitute a
          currency factor as a proxy and do NOT estimate one yourself.

    Args:
        user_id (str): REQUIRED. From the authenticated session envelope only.
        factor (str): One of "USDTRY", "EURTRY", "XU100", "XAUUSD". Case-sensitive
            upper. Anything else is refused, including any rate or inflation series.
        shock_pct (float): The hypothetical move, in percent, -100..100. Negative is a
            fall. Take it from what the user said; default to 10 only if they asked a
            conditional question without naming a size, and SAY that you assumed it.
        lookback (str | None): "1M", "3M", "6M", "1Y", "3Y", "5Y", "MAX". Null uses the
            backend default of one year.

    Returns:
        dict with exactly these top-level keys:
            factor (str), factor_name (str): the name to SAY, e.g. "Dolar/TL".
            shock_pct (float), lookback (str)
            sensitivity (dict): beta, correlation, r_squared, observation_count,
                is_statistically_reliable.
                r_squared is how much of the portfolio's past movement this factor
                explains, 0..1. A large beta with a tiny r_squared is a WEAK
                relationship — measured on a real portfolio: beta -0.68 against the
                dollar with r_squared 0.001.
            estimated_impact_pct (float), estimated_impact_value (float | null)
            statement (str): the Turkish sentence to relay.
            assumptions (list[str]): state them.
            warnings (list[str]): holdings left out and why.

    Raises:
        InvalidInputError: Unmeasurable factor, or too little shared history. Relay the
            reason; do NOT retry with a different factor and present it as the answer
            to the question that was asked.
        UpstreamUnavailableError: Service unreachable. Say the scenario could not be
            computed.

    Constraints:
        - RELAY `statement` as written, INCLUDING its closing caveat. The conditional
          and the caveat are one sentence; the first half alone is a forecast, and the
          compliance gate will block it.
        - Report `assumptions`. The linear-scaling assumption is what makes the number
          arithmetic rather than a prediction, and hiding it manufactures certainty.
        - When r_squared is small, the sentence already says the relationship is weak.
          Do not delete that clause, and do not describe the beta as though the
          relationship were strong.
        - NEVER say the factor is likely to move, or in which direction. The tool
          measures sensitivity; it observes nothing about what comes next.
        - Do NOT turn the result into a recommendation to hedge, sell or rebalance.
        - Any response built on this tool MUST pass validate_compliance_rules.
    """
    body: dict[str, Any] = {"factor": factor, "shock_pct": shock_pct}
    if lookback:
        body["lookback"] = lookback
    # Kullanıcı yolda, oturum başlığında değil: `get_risk_profile_summary`
    # ile aynı desen. Bu servis kullanıcı token'ı taşımıyor ve taşımamalı.
    payload = await backend_client.request(
        "POST", f"/risk/scenario/{user_id}", tool=SCENARIO_TOOL, json_body=body,
    )
    return _normalize_scenario(payload)


def _normalize_scenario(payload: Any) -> dict[str, Any]:
    backend_client.require(
        payload,
        ("factor", "factor_name", "sensitivity", "estimated_impact_pct", "statement"),
        SCENARIO_TOOL,
    )
    sensitivity = payload["sensitivity"]
    if not isinstance(sensitivity, dict):
        raise ContractViolationError(f"{SCENARIO_TOOL}: 'sensitivity' must be an object.")
    backend_client.require(sensitivity, ("beta", "observation_count"), SCENARIO_TOOL)
    return {
        "factor": str(payload["factor"]),
        "factor_name": str(payload["factor_name"]),
        "shock_pct": float(payload.get("shock_pct", 0.0)),
        "lookback": str(payload.get("lookback") or "1Y"),
        "sensitivity": {
            "beta": float(sensitivity["beta"]),
            # None, not 0.0. "Ölçemedik" ile "ilişki yok" karşıt iddialar ve
            # ajana zayıf uyumu SÖYLEMESİ talimat verilmiş durumda.
            "correlation": _opt_float(sensitivity.get("correlation")),
            "r_squared": _opt_float(sensitivity.get("r_squared")),
            "observation_count": int(sensitivity["observation_count"]),
            "is_statistically_reliable": bool(
                sensitivity.get("is_statistically_reliable", False)
            ),
        },
        "estimated_impact_pct": float(payload["estimated_impact_pct"]),
        "estimated_impact_value": _opt_float(payload.get("estimated_impact_value")),
        "statement": str(payload["statement"]),
        "assumptions": [str(a) for a in (payload.get("assumptions") or [])],
        "warnings": [str(w) for w in (payload.get("warnings") or [])],
    }


async def get_portfolio_stress_test(
    user_id: str, lookback: Optional[str] = None
) -> dict[str, Any]:
    """
    Reports what the user's portfolio ACTUALLY did in its worst stretches: its worst
    single days, and how it moved during each macro factor's sharpest swing. READ-ONLY.
    Nothing here is hypothetical — every figure is a day that happened.

    WHEN TO USE
        - The user asks about real bad stretches: "en kötü günüm neydi", "kriz olsa ne
          olur", "portföyüm daha önce ne kadar düştü", "dolar fırladığında ne oldu".
        - A risk answer would be more concrete with a real episode next to the
          statistics.

    WHEN NOT TO USE
        - A hypothetical move that has not happened. Use run_portfolio_scenario.
        - Ongoing volatility, drawdown or VaR. Use calculate_portfolio_risk_metrics.

    Args:
        user_id (str): REQUIRED. From the authenticated session envelope only.
        lookback (str | None): "1M", "3M", "6M", "1Y", "3Y", "5Y", "MAX". Null uses the
            backend default.

    Returns:
        dict with exactly these top-level keys:
            lookback (str), observation_count (int)
            worst_days (list[dict]): date, return_pct — the portfolio's worst days,
                worst first. Real days.
            replays (dict): factor symbol -> {start_date, end_date, factor_move_pct,
                portfolio_move_pct, trading_days}. The window where that factor moved
                hardest, and what the portfolio did across the same days.
            factor_names (dict): factor symbol -> the name to SAY.
            excluded_symbols (list[str]), warnings (list[str])

    Raises:
        UpstreamUnavailableError: Service unreachable. Say so; do not recall an episode
            from memory.

    Constraints:
        - These are OBSERVATIONS, not predictions. Report them with their dates. A
          past drawdown is not a floor and not a forecast of the next one.
        - `worst_days` are SINGLE days, not a cumulative fall. Four days of -4% are
          four separate observations, not a -16% episode, and adding them together
          describes a drawdown that never happened. Use
          calculate_portfolio_risk_metrics for the actual peak-to-trough figure.
        - A replay window covers `trading_days` sessions, not calendar days, and the
          two moves in it are measured over exactly the same sessions.
        - An empty `worst_days` means the window held too little history to produce a
          return series — say that, rather than saying the portfolio never fell.
        - `excluded_symbols` were left out of the portfolio series entirely, so every
          figure here describes the REST of the portfolio. If the list is non-empty,
          say so before quoting a percentage.
        - The two moves in a replay are CONCURRENT, not causal. The factor moving and
          the portfolio moving on the same days does not establish that one caused the
          other, and you must not say it did.
        - A factor absent from `replays` could not be measured. Do not report it as
          having had no effect — that is the opposite claim.
        - Do NOT extrapolate a worst day into an expected loss, and do NOT present it
          as a bound.
        - Any response built on this tool MUST pass validate_compliance_rules.
    """
    params: dict[str, Any] = {}
    if lookback:
        params["lookback"] = lookback
    payload = await backend_client.request(
        "GET", f"/risk/stress/{user_id}", tool=STRESS_TOOL, params=params,
    )
    backend_client.require(payload, ("lookback", "worst_days", "replays"), STRESS_TOOL)
    return {
        "lookback": str(payload["lookback"]),
        "observation_count": int(payload.get("observation_count", 0)),
        "worst_days": [
            {"date": str(row.get("date", "")), "return_pct": float(row.get("return_pct", 0.0))}
            for row in backend_client.require_list(payload, "worst_days", STRESS_TOOL)
        ],
        "replays": {
            str(symbol): _normalize_replay(row)
            for symbol, row in (payload["replays"] or {}).items()
        },
        "factor_names": {str(k): str(v) for k, v in (payload.get("factor_names") or {}).items()},
        "excluded_symbols": [str(s) for s in (payload.get("excluded_symbols") or [])],
        "warnings": [str(w) for w in (payload.get("warnings") or [])],
    }


def _normalize_replay(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{STRESS_TOOL}: each replay must be an object.")
    backend_client.require(raw, ("start_date", "end_date", "factor_move_pct"), STRESS_TOOL)
    return {
        "start_date": str(raw["start_date"]),
        "end_date": str(raw["end_date"]),
        "factor_move_pct": float(raw["factor_move_pct"]),
        "portfolio_move_pct": float(raw.get("portfolio_move_pct", 0.0)),
        "trading_days": int(raw.get("trading_days", 0)),
    }


async def simulate_position_change(
    user_id: str,
    changes: list[dict[str, Any]],
    lookback: Optional[str] = None,
) -> dict[str, Any]:
    """
    Recomputes the user's risk statistics as if named holdings changed by a given
    quantity, and returns the CURRENT and SIMULATED measurements side by side.
    READ-ONLY: it stages nothing, orders nothing, and changes no holding.

    WHEN TO USE
        - The user asks how a hypothetical trade would change their risk: "100 THYAO
          daha alsam riskim ne olur", "AKBNK'ı satsam ne değişir", "bunu alırsam
          yoğunlaşmam artar mı".

    WHEN NOT TO USE
        - The user wants to actually buy or sell. Use prepare_transaction_proposal;
          this tool cannot stage anything.
        - The user asks whether they SHOULD make the trade. This tool reports two
          measurements; choosing between them is advice, which is not permitted.
        - A macro move rather than a holding change. Use run_portfolio_scenario.

    Args:
        user_id (str): REQUIRED. From the authenticated session envelope only.
        changes (list[dict]): 1..10 items, each {"symbol": str, "quantity_delta":
            float}. Positive buys, negative sells. Take both from what the user said;
            never invent a quantity, and never propose a change of your own.
        lookback (str | None): "1M", "3M", "6M", "1Y", "3Y", "5Y", "MAX".

    Returns:
        dict:
            current (dict), hypothetical (dict): score, level, volatility, hhi,
                effective_n, max_drawdown, position_count. Any may be null.
                `score` is INVERTED: 100 is calm and 0 is the riskiest, with bands
                at 70 ("Düşük") and 45 ("Orta"). A score that FALLS means risk ROSE.
                Measured: buying 500 more of an already-dominant holding moved the
                score 35.5 -> 26.8, which is more risk, not less. Read `level`
                alongside it rather than describing the number's direction alone.
                `hhi` rises and `effective_n` falls as the portfolio concentrates.
            deltas (dict): hypothetical minus current, per metric. Null where either
                side was unmeasurable — zero would read as "no change", which is a
                different claim from "we cannot tell".
            applied (list[dict]): symbol, quantity_delta, applied (bool), note — a
                change that could NOT be applied is reported here, not dropped.
            warnings (list[str])

    Raises:
        InvalidInputError: No valuable position to compare against, or an unusable
            change. Relay the reason.
        UpstreamUnavailableError: Service unreachable.

    Constraints:
        - Present the two measurements SIDE BY SIDE. Do not say which is better,
          do not call the change an improvement, and do not recommend it. The user
          reads the comparison; you do not draw the conclusion. Stating which
          direction a figure moved is reporting; calling that direction good or bad
          is a judgement this system does not make.
        - A null delta means one side could not be measured. Say the comparison could
          not be made for that metric; zero would read as "unchanged", which is a
          different claim.
        - The simulation values the change at the CURRENT price and assumes nothing
          else about the portfolio moves. It is not a projection of what the trade
          would earn, and it says nothing about cost, fees or tax.
        - The comparison is HISTORICAL: both sides are computed over the same past
          window. A hypothetical holding is measured as though it had been held all
          along, which is what makes the two sides comparable and also what makes
          neither a forecast.
        - The system NEVER proposes the change. It comes from the user, and if they
          did not name a quantity, ask rather than assume one.
        - A change with `applied: false` did not happen. Say so; a comparison that
          silently omits it describes a portfolio the user did not describe.
        - This tool does not place an order. If the user wants to proceed, that is
          prepare_transaction_proposal and then their own confirmation on screen.
        - Any response built on this tool MUST pass validate_compliance_rules.
    """
    body: dict[str, Any] = {"changes": changes}
    if lookback:
        body["lookback"] = lookback
    payload = await backend_client.request(
        "POST", f"/risk/simulate/{user_id}", tool=SIMULATE_TOOL, json_body=body,
    )
    backend_client.require(payload, ("current", "hypothetical"), SIMULATE_TOOL)
    return {
        "current": _normalize_side(payload["current"]),
        "hypothetical": _normalize_side(payload["hypothetical"]),
        # after - before, ölçüm başına. Ölçülemeyen tarafta None kalıyor:
        # sıfır "değişmedi" diye okunur ve bu "söyleyemiyoruz"dan farklı.
        "deltas": {
            str(key): _opt_float(value)
            for key, value in (payload.get("deltas") or {}).items()
        },
        "applied": [
            {
                "symbol": str(row.get("symbol", "")),
                "quantity_delta": float(row.get("quantity_delta", 0.0)),
                "applied": bool(row.get("applied", False)),
                "note": row.get("note"),
            }
            for row in (payload.get("changes") or [])
        ],
        "warnings": [str(w) for w in (payload.get("warnings") or [])],
    }


_SIDE_FIELDS = (
    "score", "level", "volatility", "hhi", "effective_n", "max_drawdown",
    "position_count",
)


def _normalize_side(raw: Any) -> dict[str, Any]:
    """One side of the comparison. Missing figures stay missing.

    Zero would read as "no volatility" rather than "not computed", and the two
    sides are meant to be read against each other -- a fabricated zero on one
    side manufactures a difference the change did not make.
    """
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{SIMULATE_TOOL}: each side must be an object.")
    return {key: raw.get(key) for key in _SIDE_FIELDS}


def _opt_float(value: Any) -> Optional[float]:
    return None if value is None else float(value)


def register(mcp: "FastMCP") -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(run_portfolio_scenario)
    mcp.tool()(get_portfolio_stress_test)
    mcp.tool()(simulate_position_change)
