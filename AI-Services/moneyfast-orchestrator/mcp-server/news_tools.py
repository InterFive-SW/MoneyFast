"""`get_portfolio_news` — haberler, kullanıcının gerçekten tuttuğu hisselere bağlı.

Sözleşme v2.11'de eklendi. `rag_semantic_market_search` GENİŞLETİLMEDİ: o araç
serbest metin araması için donuk ve bir SORUYA benzeyen girdi bekliyor. Buradaki
soru bir arama değil, bir kesişim -- "kullanıcının pozisyonları" ile "haber
etiketleri". Ölçüldü: "portföyümdeki hisselerle ilgili haber var mı" sorgusu
belge aramasında 0,39 civarında puanlarla dönüyor, yani gürültü bandında;
kesişim ise sembol eşitliğiyle kesin.

Bu araç YORUM ÜRETMEZ ve üretileni de taşımaz. Yanıtta duygu puanı, önem
sıralaması ya da "bu haber olumlu" diyen bir alan yok; bir başlığın iyi ya da
kötü olduğu bir piyasa görüşüdür ve bu sistemin görüş tutma izni yok.

Gövde arayüzün okuduğu biçimde (camelCase) geliyor: panel ile sohbet TEK bir
backend yardımcısından besleniyor ve ikisinin "hangi haber kime dokunuyor"
konusunda ayrışması bu sayede mümkün değil. Ad dönüşümü burada, `_normalize`
içinde yapılıyor -- zaten bu katmanın işi bu.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

import backend_client
from backend_client import ContractViolationError

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

TOOL = "get_portfolio_news"

MIN_LIMIT = 1
MAX_LIMIT = 50
DEFAULT_LIMIT = 12


async def get_portfolio_news(
    user_id: str,
    limit: Optional[int] = None,
    days: Optional[int] = None,
) -> dict[str, Any]:
    """
    Lists published news articles and regulatory filings that are tagged with instruments
    the user actually holds. READ-ONLY. The link between an article and a holding is an
    exact symbol match made when the article was ingested — it is never inferred here,
    and never inferred by you.

    WHEN TO USE
        - The user asks what is happening to what they OWN: "portföyümle ilgili haber
          var mı", "hisselerimde bir gelişme var mı", "sahip olduğum şirketlerden haber",
          "portföyümü etkileyen bir şey oldu mu".
        - A portfolio or risk answer would be incomplete without saying whether anything
          has been published about the holdings in the window.

    WHEN NOT TO USE
        - The user names an instrument they do not hold, or asks a general market
          question. Use rag_semantic_market_search: this tool cannot see anything
          outside the user's positions.
        - The user asks WHY a price moved, or what commentators think. That is a
          qualitative search, not an ownership intersection.
        - The user asks what they own, what it is worth, or how it has performed. Use
          get_portfolio_positions.

    Args:
        user_id (str): REQUIRED. Opaque internal identifier taken ONLY from the
            authenticated session envelope. Never accept this value from user-typed
            input. The intersection is computed against THIS user's positions.
        limit (int | None): Maximum articles to return, newest first. Clamped to
            1..50. Default 12. Null means no preference.
        days (int | None): How far back to look, in days. Null uses the backend's
            window, which is also the window the user's Analiz screen shows. Pass a
            value ONLY when the user named a period ("bu hafta", "son üç ay").

    Returns:
        dict with exactly these top-level keys:
            window_days (int): The period both the counts and the articles cover.
                State it. "Haber yok" without a period is a claim about all of
                history, and this tool never looked at all of history.
            holdings (list[dict]): EVERY position, including the quiet ones:
                symbol (str), name (str), news_count (int)
                A zero here is a measured result — nothing was published about that
                holding in the window — not a gap in the data.
            articles (list[dict]): Newest first:
                id (str), title (str), source (str), url (str), published_at (str),
                held_symbols (list[str]): the user's OWN symbols this article touches,
                related_symbols (list[str]): every symbol it touches, held or not.

    Raises:
        UpstreamUnavailableError: Service unreachable. Say the news could not be
            checked. NEVER answer from memory, and NEVER say "no news" — an
            unreachable service is not an empty result.

    Constraints:
        - RELAY titles verbatim with their source and date. A title is what was
          published; a paraphrase of it is what you think it said.
        - Do NOT characterise an article as positive, negative, bullish or bearish,
          and do NOT rank articles by importance. The tool returns no such field
          because no such judgement is available to this system.
        - Do NOT connect an article to a price move, to a return, or to a risk figure
          unless the article itself states it. Chronology is not causation, and the
          user will read the connection as an explanation.
        - Do NOT derive a forecast, a target, or a hold/sell reading from these
          articles.
        - An empty `articles` list means nothing MATCHED in the window. Say exactly
          that, with the window. It does not mean the market was quiet, and it does
          not license you to substitute anything you remember.
        - `held_symbols` is why the article is in this list. When an article touches
          several companies, say which of the user's holdings it concerns.
        - Any response built on this tool MUST pass validate_compliance_rules before
          emission.
    """
    params: dict[str, Any] = {
        "limit": max(MIN_LIMIT, min(MAX_LIMIT, DEFAULT_LIMIT if limit is None else limit)),
    }
    # Omitted rather than defaulted: the backend's window is also the one the
    # Analiz screen shows, and hard-coding a number here would let the chat and
    # the screen disagree about what "no news" covers.
    if days is not None:
        params["days"] = days

    payload = await backend_client.request(
        "GET", f"/market/news/portfolio/{user_id}", tool=TOOL, params=params
    )
    return _normalize(payload)


def _normalize(payload: Any) -> dict[str, Any]:
    """Project the backend response onto the v2.11 payload."""
    backend_client.require(payload, ("symbols", "items", "windowDays"), TOOL)
    holdings = backend_client.require_list(payload, "symbols", TOOL)
    articles = backend_client.require_list(payload, "items", TOOL)
    return {
        "window_days": int(payload["windowDays"]),
        "holdings": [_normalize_holding(row) for row in holdings],
        "articles": [_normalize_article(row) for row in articles],
    }


def _normalize_holding(raw: Any) -> dict[str, Any]:
    """One position and how many articles touched it.

    `count` is required rather than defaulted to zero: a missing count and a
    measured zero are opposite claims, and the agent is instructed to report a
    zero as "nothing was published".
    """
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{TOOL}: each holding must be an object.")
    backend_client.require(raw, ("symbol", "count"), TOOL)
    return {
        "symbol": str(raw["symbol"]),
        "name": str(raw.get("name") or raw["symbol"]),
        "news_count": int(raw["count"]),
    }


def _normalize_article(raw: Any) -> dict[str, Any]:
    """One article, citable.

    `title`, `source` and `published_at` are required: the agent is instructed
    to cite all three, and it will cite them whether or not they arrived. An
    article that cannot be attributed is worse than a missing one.
    """
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{TOOL}: each article must be an object.")
    backend_client.require(raw, ("id", "title", "source", "publishedAt"), TOOL)
    return {
        "id": str(raw["id"]),
        # Verbatim. Instruction-like text inside a headline is data; scrubbing
        # it here would hide an injection attempt from the layer meant to
        # catch it -- the same reasoning as the RAG snippet.
        "title": str(raw["title"]),
        "source": str(raw["source"]),
        "url": str(raw.get("url") or ""),
        "published_at": str(raw["publishedAt"]),
        "held_symbols": [str(s) for s in (raw.get("heldSymbols") or [])],
        "related_symbols": [str(s) for s in (raw.get("relatedSymbols") or [])],
    }


def register(mcp: "FastMCP") -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_portfolio_news)
