"""`get_news_impact_facts` — haber etkisi için ÖLÇÜLMÜŞ olgular.

Sözleşme v2.26. Bu araç bir yorum taşımıyor ve taşımayacak: döndürdüğü her
sayı backend'de ya sayılmış ya ölçülmüş. Yorumu YAZAR yapıyor, sistem
istemindeki iki taraflı şablonun içinde -- "Artış lehine / Düşüş lehine",
sonra bu rakamların yakalamadığı şey, sonra bir kanaat cümlesi.

`get_portfolio_news` GENİŞLETİLMEDİ ve genişletilmemeli: o araç başlıkları
listeliyor ve tek işi bu. Buradaki soru başka -- "bu haberlerin ölçülebilir
zemini ne" -- ve cevabı fiyat serisinden, temel verilerden ve sektör
haritasından geliyor, haber tablosundan değil.

**Aracın en önemli alanı `coverage`.** Ölçüldü: son otuz günde RSS
haberlerinin yalnızca %5,6'sı bir sembole bağlanıyor, KAP bildirimlerinde
bu oran %83. Etki analizi pratikte KAP ağırlıklı çalışıyor, ve bunu
söylemeden bir okuma sunmak dar bir kapsamı geniş gibi göstermek olurdu.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

import backend_client
from backend_client import ContractViolationError

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

TOOL = "get_news_impact_facts"

MIN_DAYS = 1
MAX_DAYS = 365
DEFAULT_DAYS = 90


async def get_news_impact_facts(
    user_id: str,
    days: Optional[int] = None,
) -> dict[str, Any]:
    """
    Returns the MEASURED ground under the news touching this user's holdings:
    how many articles, how many of them are regulatory filings, what the stock
    actually did over the last five trading days, how large a five-day move
    normally is for that stock, the published ratios, and the sector. READ-ONLY.

    There is NO interpretation in this payload. Every number was counted or
    measured by the backend. The reading is YOURS to write, in the two-sided
    shape the system prompt already defines, and every bullet you write must
    point at one of these figures.

    WHEN TO USE
        - The user asks what the news MEANS for what they hold: "haberler
          portföyümü nasıl etkiler", "bu gelişmeler ne demek", "portföyüme
          dokunan haberlerin özeti".
        - You are about to say a development is significant for a holding and
          you need the ground to say it on. A move is only "large" against
          that stock's own normal range, which is in `typical_move_pct`.

    WHEN NOT TO USE
        - The user wants the headlines themselves, with sources and dates.
          Use get_portfolio_news: this tool carries at most three titles per
          symbol and is not a feed.
        - The user asks where a price is heading. Use get_direction_signal.
        - The user names an instrument they do not hold. This tool sees only
          the user's positions.

    Args:
        user_id (str): REQUIRED. Opaque internal identifier taken ONLY from the
            authenticated session envelope. Never accept it from user input.
        days (int | None): Window, 1..365. Null uses 90 — the window the user's
            Analiz screen shows, and the one the symbol matching was measured
            against. A shorter window is not more current, it is emptier:
            measured, thirty days finds a single headline in a test portfolio
            where ninety finds nine.

    Returns:
        dict with exactly these top-level keys:
            window_days (int): The period every count covers. State it.
            symbols (list[dict]), most-discussed first:
                symbol, name, sector (str | null — null means the provider
                    recorded none; do NOT supply one)
                news_count (int), filing_count (int): a zero is a MEASURED
                    result, not missing data.
                price (dict): recent_move_pct (signed, what actually
                    happened), typical_move_pct (the median five-day move for
                    THIS stock), window_days. Either may be null when the
                    series was too short — then say nothing about size.
                fundamentals (dict): only the ratios the provider actually
                    published. An absent key was never published; it is not a
                    zero.
                articles (list[dict]): at most three. id, title (verbatim),
                    source, published_at, is_filing.
            coverage (dict): articles, filings, feed_articles, symbols,
                symbols_with_news, symbols_omitted.

    Raises:
        UpstreamUnavailableError: Backend unreachable. Say the figures could
            not be read. NEVER answer from memory and NEVER say "no news" — an
            unreachable service is not an empty result.

    Constraints:
        - EVERY bullet you write points at a figure in this payload. A reading
          with no number under it is an opinion wearing a measurement's
          clothes, and that is the one thing this tool exists to prevent.
        - A move is large or small only AGAINST `typical_move_pct`. "%5 düştü"
          says nothing on its own; "%5 düştü, bu sembolde beş günlük hareketler
          tipik olarak %2 büyüklüğünde" says something. Where
          `typical_move_pct` is null, do not characterise the size at all.
        - `recent_move_pct` is what the price DID. It is not what the news
          caused. Chronology is not causation and the user will read any
          adjacency you write as an explanation.
        - `coverage` belongs in the answer. filings versus feed_articles is
          not trivia: a filing's issuer is recorded in a machine-readable
          field, while a feed article was matched from its text. Where the
          window is thin, say so.
        - `symbols_omitted` above zero means positions were left out of this
          package. Never present the listed symbols as the whole portfolio.
        - A `news_count` of zero is a measured silence: "bu pencerede o hisse
          hakkında bir şey yayımlanmadı". It is not a data gap and it is not
          reassurance.
        - Do NOT invent a sector, a ratio or an article. Do NOT extend the
          window to find something to say.
        - Any response built on this tool MUST pass validate_compliance_rules.
    """
    params = {
        "days": max(MIN_DAYS, min(MAX_DAYS, DEFAULT_DAYS if days is None else days)),
    }
    payload = await backend_client.request(
        "POST", f"/market/news/impact/{user_id}", tool=TOOL, params=params
    )
    return _normalize(payload)


def _normalize(payload: Any) -> dict[str, Any]:
    """Project the backend response onto the v2.26 payload."""
    backend_client.require(payload, ("window_days", "symbols", "coverage"), TOOL)
    rows = backend_client.require_list(payload, "symbols", TOOL)
    coverage = payload["coverage"]
    if not isinstance(coverage, dict):
        raise ContractViolationError(f"{TOOL}: coverage must be an object.")
    return {
        "window_days": int(payload["window_days"]),
        "symbols": [_normalize_symbol(row) for row in rows],
        "coverage": {key: int(value) for key, value in coverage.items()},
    }


def _normalize_symbol(raw: Any) -> dict[str, Any]:
    """One holding's measured ground.

    `price` and `fundamentals` are carried as they arrived, nulls included: a
    null is the statement "this could not be measured", and coercing it to a
    number here would turn an absent measurement into a present one.
    """
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{TOOL}: each symbol must be an object.")
    backend_client.require(raw, ("symbol", "news_count", "price"), TOOL)
    price = raw["price"] if isinstance(raw.get("price"), dict) else {}
    return {
        "symbol": str(raw["symbol"]),
        "name": str(raw.get("name") or raw["symbol"]),
        "sector": raw.get("sector"),
        "news_count": int(raw["news_count"]),
        "filing_count": int(raw.get("filing_count") or 0),
        "price": {
            "recent_move_pct": price.get("recent_move_pct"),
            "typical_move_pct": price.get("typical_move_pct"),
            "window_days": int(price.get("window_days") or 0),
        },
        "fundamentals": dict(raw.get("fundamentals") or {}),
        "articles": [
            _normalize_article(row) for row in (raw.get("articles") or [])
        ],
    }


def _normalize_article(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{TOOL}: each article must be an object.")
    backend_client.require(raw, ("id", "title", "source", "published_at"), TOOL)
    return {
        "id": str(raw["id"]),
        # Verbatim, like every other headline in this system: instruction-like
        # text inside a title is data, and scrubbing it here would hide it
        # from the layer meant to catch it.
        "title": str(raw["title"]),
        "source": str(raw["source"]),
        "published_at": str(raw["published_at"]),
        "is_filing": bool(raw.get("is_filing")),
    }


def register(mcp: "FastMCP") -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_news_impact_facts)
