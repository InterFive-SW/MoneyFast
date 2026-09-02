"""`get_portfolio_report` — sistemin ölçtüğü her şeyin tek belgede toplanması.

Sözleşme v2.18. Proje dokümanı bu raporu adıyla istiyor: *"'Portföyü Yeniden
Dengele' ve 'Detaylı Rapor Oluştur' butonlarıyla tek tıkla akıllı öneri ve
kapsamlı analiz raporu alınır."*

YENİ ÖLÇÜM YOK ve YENİ CÜMLE YOK. Bölümlerin metni backend'de, `report.py`'de
bir kez kuruluyor; ekran, PDF ve bu araç aynı metni okuyor. Bu depoda
tekrarlanan ders: iki yüzey aynı şeyi ayrı ayrı yazarsa ayrışırlar.

YALNIZCA CÜMLELER TAŞINIYOR, satırlar değil. Ölçüldü: risk turunun sentez
gövdesi sağlayıcının 8.000 token'lık istek sınırına zaten dayanmış durumda ve
raporun tam hâli altı bölümün satırlarını birden taşır. Satırlar ekranın ve
PDF'in işi; yazarın işi bölüm başlığı ve o bölümün tek cümlesi.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

import backend_client
from backend_client import ContractViolationError

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

TOOL = "get_portfolio_report"


async def get_portfolio_report(user_id: str) -> dict[str, Any]:
    """
    Retrieves the user's DETAILED REPORT: every measurement this system holds about
    their portfolio, assembled into one document. READ-ONLY.

    WHEN TO USE
        - "detaylı rapor", "portföy raporu", "raporumu oluştur", "her şeyi özetle",
          "portföyümün genel durumu nedir".
        - A question that spans several areas at once — what I hold AND how risky it
          is AND how far from my target — where answering with one tool would leave
          most of it out.

    WHEN NOT TO USE
        - A single narrow question. "AKBNK kaç lira" is get_market_data; pulling the
          whole report for it is waste, and the answer would bury the figure.
        - Anything about an instrument the user does not own.

    Args:
        user_id (str): The authenticated user, from the session envelope. Never a
            value the user typed.

    Returns:
        dict with exactly these top-level keys:
            generated_at (str): when the DOCUMENT was assembled, ISO 8601 UTC.
            currency_code (str): the currency every figure in the report is in.
                Foreign holdings are already converted into it; the report never
                adds two currencies together.
            as_of (str): when the PRICES in it were true. NOT the same as
                generated_at, and the difference is the delay this product is
                obliged to disclose. A report assembled at 14:05 from 13:47 quotes
                is eighteen minutes old, and saying "14:05 itibarıyla" would be a
                false freshness claim.
            is_delayed (bool), delay_minutes (int): the disclosure itself.
            sections (list[dict]): one per area, in the order the report presents
                them, each with:
                    key (str): stable identifier — overview, allocation, drift, risk,
                        cash_flow, positions.
                    title (str): the section heading, already in Turkish.
                    summary (str): ONE ready Turkish sentence, composed by the
                        backend. Relay it as written.

                The six sections, in the order they arrive:
                    overview   -- total value, cash, position count, and any holding
                                  left out of the total because it has no price.
                    allocation -- weight per bucket: cash, BIST equity, US equity,
                                  gold, currency.
                    drift      -- those weights against a target the USER entered.
                                  When no target exists the section says so; that is
                                  NOT zero drift.
                    risk       -- the measured 0-100 score (100 is calm, not risky),
                                  the level, the comparison against the tolerance the
                                  user declared, and which assessed product groups
                                  their holdings sit in.
                    cash_flow  -- monthly income, spending and what was left over.
                    positions  -- every priced holding, largest first.

    Raises:
        InvalidInputError: No user_id.
        UpstreamUnavailableError: Service unreachable. Say the report could not be
            produced. NEVER assemble one from memory or from earlier turns.

    Constraints:
        - The `summary` sentences are the report. Relay them; do not reword, reorder
          or merge them. They are composed once in the backend precisely so the
          screen, the PDF and this answer cannot disagree.
        - A section is present even when it has no data, and says so. Do NOT drop it:
            a missing section reads as a broken report rather than as an absent
            measurement. Measured — 3 of 23 users have any banking records at all.
        - This report DESCRIBES; it does not advise. It contains a drift from a target
          the USER set and a risk level beside a tolerance the USER declared. Neither
          is an instruction, and turning "hedefin 30,4 puan üzerinde" into "bu kadar
          satın" is investment advice this product does not give.
        - Do not add a section of your own, do not compute a figure the report does
          not carry, and do not rank the sections by importance.
        - State the price delay with the report, from `as_of` and `delay_minutes`,
          in this product's single wording. Do NOT date the figures with
          `generated_at`: that is when the document was built, not when its prices
          were true, and using it would overstate their freshness.
        - The risk score runs 0-100 where 100 is CALM. A score of 36 is not "36%
          risky" and not a grade; report it with the band that comes beside it.
        - The report may be long. Do not answer it with a wall of numbers: lead with
          the section summaries, which are already written to be read.
        - Any response containing these figures MUST pass validate_compliance_rules
          before emission.
    """
    wanted = str(user_id or "").strip()
    if not wanted:
        raise backend_client.InvalidInputError(f"{TOOL}: user_id gerekiyor.")

    payload = await backend_client.request(
        "GET", f"/analytics/report/{wanted}", tool=TOOL
    )
    backend_client.require(payload, ("generated_at", "sections"), TOOL)
    sections = backend_client.require_list(payload, "sections", TOOL)
    return {
        "generated_at": str(payload["generated_at"]),
        "currency_code": str(payload.get("currency_code") or "TRY"),
        "as_of": str(payload.get("as_of") or payload["generated_at"]),
        "is_delayed": bool(payload.get("is_delayed", False)),
        "delay_minutes": int(payload.get("delay_minutes") or 0),
        # `lines` ve `rows` BİLEREK taşınmıyor: ekranın ve PDF'in işi, ve
        # altı bölümün satırları birden sentez gövdesini sağlayıcı sınırının
        # üstüne çıkarır -- bu turda ölçülmüş bir sınır.
        "sections": [_normalize_section(row) for row in sections],
    }


def _normalize_section(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{TOOL}: each section must be an object.")
    backend_client.require(raw, ("key", "title"), TOOL)
    return {
        "key": str(raw["key"]),
        "title": str(raw["title"]),
        "summary": str(raw.get("summary") or ""),
    }


def register(mcp: "FastMCP") -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_portfolio_report)
