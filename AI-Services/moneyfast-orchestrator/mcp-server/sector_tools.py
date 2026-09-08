"""`get_sector_map` — hangi enstrüman hangi sektörde.

Sözleşme v2.25'te eklendi ve KAPATILAN BİR BOŞLUK: `sector_by_symbol()`
backend'de vardı ve ısı haritası ile dağılım kırılımlarını besliyordu, ama
hiçbir MCP aracı sektör döndürmüyordu. "Bankacılık sektörü bu haberden nasıl
etkilenir" sorusunun veri yolu yoktu -- ajan sektörü ya bilmiyordu ya da
kendi bildiğinden uyduruyordu, ve ikincisi ölçülmüş sektörle uydurulmuş
sektörü ayırt edilemez yapıyor.

Kaynak TEK: `instrument_fundamentals.sector`, sağlayıcı verisi. Elle yazılmış
sektör yok. Sektörü olmayan enstrüman haritada HİÇ GÖRÜNMÜYOR ve kaçının
dışarıda kaldığı sayılıyor -- ölçülmüş bir boşluk, uydurulmuş bir değer
değil.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

import backend_client
from backend_client import ContractViolationError

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

TOOL = "get_sector_map"

#: Sektör başına taşınan en fazla sembol.
#:
#: Ölçüldü: süzgeçsiz yanıt 31 KB ve en kalabalık sektörde 170 sembol var --
#: bir sohbet turunda tek başına dakikalık token sınırını aşıyor ve
#: kullanıcı "veri tek seferde işleyebileceğimden büyük çıktı" cevabı
#: alıyordu.
#:
#: Kırpılan sembol sayısı SÖYLENİYOR (`truncated`). Sessizce kısaltılmış bir
#: üyelik listesi, "sektörde bunlar var" diyen bir cümleyi yanlış yapardı;
#: sayısı yazılı olduğunda cümle "bunlar ve N tane daha" oluyor.
MAX_SYMBOLS_PER_SECTOR = 25


async def get_sector_map(sector: Optional[str] = None) -> dict[str, Any]:
    """
    Returns which instrument belongs to which sector, as recorded by the data
    provider. READ-ONLY. Not user-specific.

    WHEN TO USE
        - A question about a SECTOR rather than an instrument: "bankacılık
          sektörü bu haberden nasıl etkilenir", "havacılık hisseleri", "enerji
          sektöründe ne var".
        - You need to say which companies a sector-wide development reaches,
          and you must not guess the membership.

        - A news item is about an industry rather than a company -- a rate
          decision, a fuel price, a regulation -- and you need to name which
          instruments the channel actually reaches. Without this tool the only
          way to answer is from memory, and sector membership is exactly the
          kind of fact a model recalls confidently and wrongly.

    WHEN NOT TO USE
        - The user names an instrument. Use get_market_data or
          get_technical_signals; this tool carries no price and no measurement.
        - You want the user's own exposure by sector. That is in the risk
          metrics (`concentration` breaks down by sector), already weighted by
          what they hold. This tool has no idea what anyone owns.
        - The user asks which sector to invest in. That is a ranking question
          and this tool does not answer it; nothing here says one sector is
          better placed than another.

    Args:
        sector (str | None): Narrow to one sector, matched case-insensitively
            against the provider's own label. Null returns every sector, and
            you should pass one whenever the user named a sector: the full map
            is large and most of it will be irrelevant to the question.

    Returns:
        dict with exactly these top-level keys:
            sectors (list[dict]): sector (str), symbols (list[str]) capped at
                25, and truncated (int) — how many members were NOT listed.
                When truncated is above zero, say "ve N tane daha"; a silently
                shortened membership makes "these are the ones" a false
                sentence.
            unclassified (int): how many tradable instruments have NO recorded
                sector. State it when you speak about a sector's coverage: a
                map that does not say what it is missing reads as complete.

    Raises:
        UpstreamUnavailableError: Backend unreachable. Say the sector mapping
            could not be read; NEVER answer from memory. Which company sits in
            which sector is exactly the kind of fact a model recalls wrongly.

    Constraints:
        - The membership here is the provider's, not yours. NEVER add a company
          to a sector because you believe it belongs there, and never rename a
          sector into something that reads better in Turkish.
        - An instrument that is absent has NO recorded sector. That is a
          measured gap; do not fill it and do not call it "diğer".
        - This tool says nothing about price, performance or risk. A sector
          membership is not a reason to expect anything.
        - Do NOT rank sectors, and do NOT call one attractive.
        - A sector is a GROUPING, not a mechanism. "Bankacılık sektöründe" is
          not an explanation of anything; if you cannot name how a development
          reaches a company, the fact that it shares a sector label with
          another company is not a substitute.
        - Sector labels come from the provider in English ("Financial
          Services", "Industrials"). Relaying one in Turkish is fine, but the
          label you relay must be a translation of the one you were given --
          never a category of your own that happens to sound similar.
        - `unclassified` is not noise. When you say "this reaches the whole
          sector", the instruments with no recorded sector are outside your
          answer and the user cannot tell unless you say so.
        - Do NOT combine this with a price reading to imply a sector-wide move.
          Two companies sharing a label is not evidence that they move
          together; the measurement for that is correlation, and it lives in
          the risk metrics.
        - Any response built on this tool MUST pass validate_compliance_rules.
    """
    params = {"sector": sector} if sector else None
    payload = await backend_client.request(
        "GET", "/market/sectors", tool=TOOL, params=params
    )
    return _normalize(payload)


def _normalize(payload: Any) -> dict[str, Any]:
    """Project the backend response onto the v2.25 payload.

    `symbols` (the flat symbol -> sector dict) is NOT carried. The agent
    answers sector questions, and a thousand-entry map costs tokens it never
    reads -- `_slim_results` with the same reasoning. `unclassified` IS
    carried, because a map that does not say what it is missing reads as
    complete.
    """
    backend_client.require(payload, ("sectors", "unclassified"), TOOL)
    rows = backend_client.require_list(payload, "sectors", TOOL)
    return {
        "sectors": [_normalize_sector(row) for row in rows],
        "unclassified": int(payload["unclassified"]),
    }


def _normalize_sector(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{TOOL}: each sector must be an object.")
    backend_client.require(raw, ("sector", "symbols"), TOOL)
    symbols = [str(symbol) for symbol in (raw.get("symbols") or [])]
    return {
        "sector": str(raw["sector"]),
        "symbols": symbols[:MAX_SYMBOLS_PER_SECTOR],
        # Kaçı listelenmedi. Sıfır da yazılıyor: alanın yokluğu ile sıfır
        # olması aynı şey değil ve ilki "kırpılmadı mı, yoksa sayılmadı mı"
        # sorusunu açık bırakırdı.
        "truncated": max(0, len(symbols) - MAX_SYMBOLS_PER_SECTOR),
    }


def register(mcp: "FastMCP") -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_sector_map)
