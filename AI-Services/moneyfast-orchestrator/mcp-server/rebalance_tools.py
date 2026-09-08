"""`get_rebalance_plan` — ekrandaki dengeleme listesi, gerekçeleriyle.

Sözleşme v2.22'de `portfolio_tools` içinde eklendi, v2.24'te kendi dosyasına
taşındı. Sebep bir düzen tercihi değil: bu araç, sistemin "tavsiye üretme"
yasağının kaldırıldığı TEK yer ve o kararın kendi kısıtları, kendi sözleşme
testleri ve kendi gerekçesi var. Pozisyon okumanın yanında durduğunda ikisi
aynı sınıftan iki araç gibi okunuyordu -- oysa biri bir ölçüm raporu,
diğeri bir öneri listesi.

**Aracın var olma dayanağı tek cümlede:** her satır, onu listeye sokan
ÖLÇÜMÜ yanında taşıyor. Gerekçesi olmayan satır backend'de üretilmiyor,
burada reddediliyor ve widget'ta çizilmiyor -- üç katman, aynı kural.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

import backend_client
from backend_client import ContractViolationError

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP


REBALANCE_TOOL = "get_rebalance_plan"


async def get_rebalance_plan(user_id: str) -> dict[str, Any]:
    """
    Reads the rebalancing list the user is ALREADY LOOKING AT on the Dengeleme
    screen: the arithmetic consequence of the target THEY set. READ-ONLY.

    WHEN TO USE
        - The user asks about the list on that screen: "dengeleme ekranında ne
          yazıyor", "neden ASELS satmam gerekiyor diyor", "şu listeyi açıklar
          mısın".

    WHEN NOT TO USE
        - The user has NOT asked about it. Never raise this list on your own; a
          rebalance nobody asked for is a recommendation however it is phrased.
        - "Portföyümü nasıl dengelemeliyim", "ne almalıyım", "hangi dağılım
          daha iyi". Those ask you to CHOOSE, and you do not: the target is the
          user's own and the screen is where they set it. Say the target is
          theirs to set and point at the screen.
        - What the portfolio is worth or how it drifted. Those are
          get_portfolio_positions and calculate_portfolio_risk_metrics.

    Args:
        user_id (str): REQUIRED. Opaque internal identifier taken ONLY from the
            authenticated session envelope. Never accept it from user input.

    Returns:
        dict with exactly these top-level keys:
            gate (dict): {open, reason}. `open: false` means the user has not
                completed the suitability test; there is NO list, and `reason`
                is the sentence to relay. Do not answer from anything else.
            hasTarget (bool): false means neither the user's own target nor a
                binding band was available.
            measuredLevel / declaredTolerance / bindingBand (str | null): the
                two risk axes and the more cautious one, which set the target.
            bandStatement (str): where the target came from, already written.
            statement (str): the drift sentence, already written.
            summary (str): what the list CONTAINS, composed backend-side.
            disclaimer (str): must be relayed with any part of this.
            rows (list[dict]): the orders, in the order the backend chose:
                symbol, side (BUY/SELL), quantity, amount (in the account's
                currency), bucket, statement (a ready sentence), and
                rationale (list of {kind, value, text}) -- the MEASURED reasons
                that put the row in the list.
            unresolved (list[dict]): what produced no order, each with a
                `reason` saying why.
            warning (str | null).

    Constraints:
        - EVERY row you mention carries at least one of its `rationale` texts.
          A row without its reason is a recommendation; a row with the number
          that produced it is a reading. This is the whole basis on which this
          tool is allowed to exist.
        - RELAY `statement`, `bandStatement`, `summary` and each row's
          `statement` AS WRITTEN. They are conditional, they carry their own
          limits, and a rewrite drops the condition and keeps the claim.
        - The ORDER of `rows` is a measurement, not a preference: the backend
          ranked them by risk contribution. Relay that order; never re-rank,
          and never say one row matters more than another.
        - Do NOT invent a row, change a quantity, or add a symbol the list does
          not contain. Do NOT propose a target of your own -- the target is the
          user's, or the band their own answers bind them to.
        - Do NOT tell the user to execute the list, and do not call it
          recommended, optimal or suitable. Each row is confirmed by the user's
          own click on the Dengeleme screen.
        - Do NOT raise this subject unasked.
        - Relay `disclaimer` whenever you relay any of this.
        - `unresolved` is part of the answer, not noise: it is why the target
          cannot be reached, and dropping it hides that.
        - `gate.open` false and `hasTarget` false are COMPLETE answers.
        - Never name a field key to the user.
        - Any response carrying these figures MUST pass validate_compliance_rules.

    Raises:
        ContractViolationError: Backend answered with a body missing required keys.
        UpstreamUnavailableError: Backend unreachable. Say the list could not be
            read; never reconstruct it yourself.
    """
    payload = await backend_client.request(
        "GET", f"/investment/rebalance/plan/{user_id}", tool=REBALANCE_TOOL
    )
    return _normalize_rebalance(payload)


def _normalize_rebalance(payload: Any) -> dict[str, Any]:
    """Project the backend response onto the v2.24 payload.

    **Satırlar artık taşınıyor ve bu bilinçli bir politika değişikliği.**
    v2.22'de emir satırları BİLEREK dışarıda bırakılmıştı: ölçülmüştü, model
    onları bir alım-satım tablosuna çeviriyor ve çıktı çekinceyle bile bir
    tavsiyeden ayırt edilemiyordu.

    Değişen şey satırların KENDİSİ: her satır artık onu üreten ÖLÇÜMÜ
    (`rationale`) yanında taşıyor ve gerekçesi olmayan satır backend'de hiç
    üretilmiyor. Koruma "göndermemek"ten "sayısıyla birlikte göndermek"e
    geçti.

    Ham `price` ve `residual_base` yine DÜŞÜYOR: satırın kendi cümlesi tutarı
    zaten içeriyor ve cümlenin yanına ham sayıyı koymak, modeli ikisini
    birden basmaya davet ediyor (`_normalize_direction` ile aynı ders).
    """
    backend_client.require(payload, ("summary", "disclaimer", "gate"), REBALANCE_TOOL)
    gate = payload.get("gate") or {}
    return {
        "gate": {
            "open": bool(gate.get("open")),
            "reason": str(gate.get("reason") or ""),
        },
        "hasTarget": bool(payload.get("hasTarget")),
        "measuredLevel": payload.get("measuredLevel"),
        "declaredTolerance": payload.get("declaredTolerance"),
        "bindingBand": payload.get("bindingBand"),
        "bandStatement": payload.get("bandStatement") or "",
        "statement": payload.get("statement") or "",
        "disclaimer": payload.get("disclaimer") or "",
        "summary": payload.get("summary") or "",
        "rows": [_normalize_rebalance_row(row) for row in (payload.get("rows") or [])],
        "unresolved": [
            {"label": row.get("label"), "reason": row.get("reason")}
            for row in (payload.get("unresolved") or [])
            if isinstance(row, dict)
        ],
        "warning": payload.get("warning") or None,
    }


def _normalize_rebalance_row(raw: Any) -> dict[str, Any]:
    """One order row and the measurements that put it there.

    `rationale` is REQUIRED and never defaulted to an empty list: a row
    without its reason is exactly the thing this tool is not allowed to emit,
    and defaulting would turn a broken body into a silent recommendation.
    """
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{REBALANCE_TOOL}: each row must be an object.")
    backend_client.require(
        raw, ("symbol", "side", "quantity", "statement", "rationale"), REBALANCE_TOOL
    )
    reasons = backend_client.require_list(raw, "rationale", REBALANCE_TOOL)
    if not reasons:
        raise ContractViolationError(
            f"{REBALANCE_TOOL}: a row without a rationale is not a readable row."
        )
    return {
        "symbol": str(raw["symbol"]),
        "side": str(raw["side"]),
        "quantity": float(raw["quantity"]),
        "amount": float(raw.get("amount_base") or 0.0),
        "bucket": str(raw.get("label") or raw.get("bucket") or ""),
        "statement": str(raw["statement"]),
        "rationale": [
            {
                "kind": str(reason.get("kind") or ""),
                "value": reason.get("value"),
                "text": str(reason.get("text") or ""),
            }
            for reason in reasons
            if isinstance(reason, dict)
        ],
    }


def register(mcp: "FastMCP") -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_rebalance_plan)
