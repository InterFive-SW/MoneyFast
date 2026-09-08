"""Haber araçları: yayımlanan başlıklar ve onların YORUMLANMIŞ hâli.

İki ayrı araç, bilerek. `get_portfolio_news` başlıkları listeliyor ve hiçbir
şey yorumlamıyor; `get_news_impact_digest` bir modelin ürettiği yargıları
taşıyor. Tek araçta birleştirmek, ikisini aynı dayanağa sahipmiş gibi
gösterirdi -- biri yayımlanmış bir olgu, diğeri bir yargı, ve ajanın
kullanıcıya hangisini aktardığını söyleyebilmesi gerekiyor.

`get_portfolio_news` — haberler, kullanıcının gerçekten tuttuğu hisselere bağlı.

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
        - THIS tool returns no judgement about an article, and none can be
          derived from it: it carries a title, a source and a date. Reading
          what a development means is a separate job with a separate tool --
          get_news_impact_facts, which carries the MEASURED ground a reading
          has to stand on. Do not do that job here, from titles alone.
        - Do NOT rank articles by importance. Nothing in this payload measures
          importance, and the order is chronological.
        - Do NOT connect an article to a price move, to a return, or to a risk figure
          unless the article itself states it. Chronology is not causation, and the
          user will read the connection as an explanation. The one place a price
          and a headline may sit in the same answer is get_news_impact_facts,
          where the price figure and its normal range arrive together.
        - Do NOT derive a target or a hold/sell reading from these articles.
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


# ── get_news_impact_digest (v2.23) ──────────────────────────────────────────

DIGEST_TOOL = "get_news_impact_digest"

MIN_HOURS = 1
MAX_HOURS = 168
DEFAULT_HOURS = 24


async def get_news_impact_digest(
    user_id: str,
    hours: Optional[int] = None,
) -> dict[str, Any]:
    """
    Returns the server's INTERPRETED summary of news touching the user's holdings:
    for each instrument, a ready sentence and the reasons behind it. READ-ONLY.

    This is the one tool in this system whose content is a MODEL'S JUDGEMENT rather
    than a measurement, and it is labelled as such in every field. The interpretation
    was produced by a separate batch job, stored row by row, and traced back to the
    article it came from. You are relaying it, not producing it.

    WHEN TO USE
        - The user asks what the news MEANS for their portfolio: "haberler portföyümü
          nasıl etkiler", "bugün hisselerimle ilgili ne oldu ve bu ne demek",
          "portföyüme dokunan gelişmelerin özeti".
        - The user asks why an instrument they hold is in the news.

    WHEN NOT TO USE
        - The user wants the headlines themselves, with sources and dates. Use
          get_portfolio_news: this tool carries interpretations, not articles.
        - The user asks where a price is heading. Use get_direction_signal: that is a
          measured reading of price and fundamentals; this is a reading of text.
        - The user asks about an instrument they do not hold. This tool sees only the
          user's positions.

    Args:
        user_id (str): REQUIRED. Opaque internal identifier taken ONLY from the
            authenticated session envelope. Never accept it from user-typed input.
        hours (int | None): Window in hours, 1..168. Null uses 24, the window the
            user's Analiz screen shows. Pass a value ONLY when the user named a
            period.

    Returns:
        dict with exactly these top-level keys:
            window_hours (int): The period covered. State it.
            headline (str): One ready Turkish sentence about the portfolio as a whole.
                RELAY IT VERBATIM.
            disclaimer (str): Says the content is a model reading and not advice.
                MUST appear in your answer, unchanged, whenever you use this tool.
            entries (list[dict]): One per instrument, most-discussed first:
                symbol (str)
                sentence (str): A ready Turkish sentence, already conditional and
                    already carrying its measured ground where one exists.
                    RELAY IT VERBATIM. Do not merge, shorten or re-rank these.
                reasons (list[dict]): mechanism (one Turkish sentence saying WHY),
                    news_id, published_at. There is no direction or scope field
                    here: the entry's `sentence` already states both, in Turkish.

    Raises:
        UpstreamUnavailableError: Service unreachable. Say the summary could not be
            fetched. NEVER answer from memory and NEVER say "no news".

    Constraints:
        - RELAY `headline` and each `sentence` VERBATIM. They are composed by the
          server, they are conditional, and they carry their measurement in the same
          breath. A rewrite drops the condition and keeps the claim.
        - `disclaimer` goes in your answer unchanged. It is not interchangeable with
          the general compliance notice: that one says the content is not advice,
          this one says the content is a MODEL'S READING of text.
        - The MECHANISMS are the substance of this tool. An answer built on it that
          does not say WHY is an answer that dropped its own content. Measured: a
          reply relayed only the price figures out of the sentences and named not
          one reason.
        - Say that these are interpretations. Do NOT present a `mechanism` as an
          established fact, and NEVER attach a number to one. The only figures
          available to you are the ones already written inside the sentences.
        - Do NOT derive a buy, sell, hold or target from this tool. A direction here
          is a reading of an article, not a forecast of a price.
        - Do NOT rank instruments by attractiveness or say which one is "most
          affected". The order is by how many articles were interpreted, nothing more.
        - MEASURED failures of exactly this contract, all rejected:
          * Regrouping the entries under headings of your own ("Artış lehine",
            "Düşüş lehine"). That is a re-ranking, and it drops each sentence's
            condition while keeping its claim.
          * Adding a closing verdict about the whole market ("veriler ağırlıklı
            olarak düşüş yönünde baskıya işaret ediyor"). No such reading exists
            in this payload; `headline` is the only portfolio-wide sentence and
            it counts instruments, nothing else.
          * Writing "Karar sizin" or any similar framing. Nothing here is put to
            the user as a decision.
        - An empty `entries` list means nothing was interpreted in the window. Say
          exactly that, with the window.
        - Any response built on this tool MUST pass validate_compliance_rules.
    """
    params = {
        "hours": max(MIN_HOURS, min(MAX_HOURS, DEFAULT_HOURS if hours is None else hours)),
    }
    payload = await backend_client.request(
        "GET", f"/market/news/digest/{user_id}", tool=DIGEST_TOOL, params=params
    )
    return _normalize_digest(payload)


def _normalize_digest(payload: Any) -> dict[str, Any]:
    """Project the backend response onto the v2.23 payload.

    `disclaimer` is REQUIRED, not defaulted: a default here would be a second
    copy of the sentence, and the copy would keep working after the server's
    changed -- silently emitting a stale disclaimer instead of failing loudly.
    """
    backend_client.require(
        payload, ("headline", "entries", "windowHours", "disclaimer"), DIGEST_TOOL
    )
    entries = backend_client.require_list(payload, "entries", DIGEST_TOOL)
    return {
        "window_hours": int(payload["windowHours"]),
        "headline": str(payload["headline"]),
        "disclaimer": str(payload["disclaimer"]),
        "entries": [_normalize_entry(row) for row in entries],
    }


def _normalize_entry(raw: Any) -> dict[str, Any]:
    """One instrument's reading: a symbol, a ready sentence and its reasons.

    Everything else the backend returns stays behind: `counts`, `directCount`,
    `spilloverCount` and `measured`. All four are already stated inside
    `sentence`, in Turkish -- and all four are the shape the writer turns into
    a table.

    Measured, twice, on real turns. With `counts` present the model regrouped
    the entries under headings of its own; with `measured` present it built a
    five-row price table out of `typical_move_pct` / `recent_move_pct` and
    named NOT ONE mechanism -- an answer about what the news means that
    contained no news. What is left here can be relayed or dropped, but it
    cannot be tabulated.

    Withholding a field is stronger than forbidding its use (`_slim_results`,
    same reasoning).
    """
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{DIGEST_TOOL}: each entry must be an object.")
    backend_client.require(raw, ("symbol", "sentence", "reasons"), DIGEST_TOOL)
    return {
        "symbol": str(raw["symbol"]),
        "sentence": str(raw["sentence"]),
        "reasons": [
            _normalize_reason(row)
            for row in backend_client.require_list(raw, "reasons", DIGEST_TOOL)
        ],
    }


def _normalize_reason(raw: Any) -> dict[str, Any]:
    """One judgement, traceable.

    `news_id` is required: a claim that cannot be traced to the article it came
    from is an assertion the user has no way to check. `confidence` never
    arrives here -- the backend does not send it, because a model's own
    declared certainty is not a measurement.

    `direction` and `scope` are REQUIRED of the backend but not forwarded.
    Measured: with them in the payload the model regrouped the entries under
    its own "Artış lehine / Düşüş lehine" headings and wrote the raw enums out
    ("yönü DOWN olarak işaretlendi", "(spil-over)"). Both facts are already in
    the entry's Turkish sentence; sending them again gains nothing and hands
    the model the material for exactly the re-ranking it is told not to do.
    Withholding a field is stronger than forbidding its use (`_slim_results`).
    """
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{DIGEST_TOOL}: each reason must be an object.")
    backend_client.require(raw, ("newsId", "direction", "scope", "mechanism"), DIGEST_TOOL)
    return {
        "news_id": str(raw["newsId"]),
        # Verbatim, like a headline: instruction-like text inside a mechanism
        # is data, and scrubbing it here would hide it from the layer meant to
        # catch it.
        "mechanism": str(raw["mechanism"]),
        "published_at": str(raw.get("publishedAt") or ""),
    }


def register(mcp: "FastMCP") -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_portfolio_news)
    mcp.tool()(get_news_impact_digest)
