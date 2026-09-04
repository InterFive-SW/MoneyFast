"""`resolve_instruments` — şirket adından sembole.

Sözleşme v2.19'da eklendi. Sebebi ölçülmüş bir hata: kullanıcı "türk hava
yolları ne durumda yeni haberler var mı gündemde?" diye sordu ve cevapta
kaynak olarak ÜÇ EKGYO bildirimi listelendi.

Yönlendirici zaten `entities.company_names` çıkarıyordu -- istem bunu
istiyor -- ama orkestratörde bu alanı okuyan tek bir satır yoktu. "Türk Hava
Yolları" bir ad, sembol değil; `_first_ticker` `None` döndü, arama süzgeçsiz
çalıştı ve 0,45 kosinüs eşiğini geçen ilk sekiz Türkçe bildirim geri geldi.
Model hatası değil: hiç kimse adı THYAO'ya çevirmedi.

`rag_semantic_market_search` GENİŞLETİLMEDİ. O araç anlamsal benzerlik
arıyor; buradaki soru bir arama değil, bir SÖZLÜK araması: "türk hava
yolları" ile THYAO arasındaki bağ ölçülen bir benzerlik değil, kayıtlı bir
gerçek. Backend'in `GET /market/search` ucu bunu zaten yapıyor ve Türkçe
katlamasıyla yapıyor (`sise` yazan `ŞİŞE`yi buluyor).

Bu araç HİÇBİR ŞEY ÖNERMEZ ve fiyat taşımaz: sembol, ad, borsa. Fiyat
sormak `get_market_data`'nın işi ve iki araçtan iki farklı fiyat çıkması
mümkün olmamalı.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

import backend_client
from backend_client import ContractViolationError

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

TOOL = "resolve_instruments"

MIN_LIMIT = 1
MAX_LIMIT = 10
DEFAULT_LIMIT = 5

#: Backend'in kendi tavanı. Daha büyüğünü istemek 422 döndürür.
BACKEND_MAX_LIMIT = 25

MIN_QUERY_LENGTH = 2


async def resolve_instruments(
    query: str,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """
    Turns a company NAME into the ticker symbols this system actually knows. READ-ONLY.
    A lookup, not a search: the link between "Türk Hava Yolları" and THYAO is a recorded
    fact in the instrument universe, not a similarity you should estimate.

    WHEN TO USE
        - The user named a company in words rather than by code: "türk hava yolları",
          "garanti bankası", "şişe cam", "apple". Resolve it BEFORE any tool that takes
          a symbol.
        - You are about to search for news or filings about a company and you have its
          name but not its code.

    WHEN NOT TO USE
        - The user already gave a symbol (THYAO, AAPL). Use it directly; a lookup would
          only add latency and a chance to pick a near-neighbour by mistake.
        - You want prices, ratios or rankings. Use get_market_data; this tool carries no
          price and never will, so that two tools cannot report two different prices.
        - You want to know WHETHER a company exists as a real-world entity. This tool
          answers a narrower question: whether THIS system carries an instrument for it.
        - The user asked about a sector, a theme or "the market" rather than a company.
          There is nothing to resolve; pass the question to the retriever as written.

    WHAT THIS PREVENTS
        A user asked "türk hava yolları ne durumda yeni haberler var mı gündemde?" and
        the answer cited three EKGYO filings. Nothing had resolved the NAME to THYAO, so
        the document search ran with no instrument filter and returned whatever cleared
        the similarity floor -- in a corpus of ~29.000 Turkish filings, that is filing
        boilerplate about an unrelated company. Resolving first is what makes the filter
        possible; without a symbol there is nothing to filter on.

    Args:
        query (str): REQUIRED. The company name or partial name, as the user wrote it.
            Turkish folding is applied by the backend, so "sise" finds "ŞİŞE" and the
            user's own spelling is usually enough. At least 2 characters.
        limit (int | None): Maximum suggestions. Clamped to 1..10, default 5.

    Returns:
        dict with exactly these top-level keys:
            query (str): What was looked up, echoed so the answer can name it.
            instruments (list[dict]): Best match first. Each:
                symbol (str), name (str), market (str | None), currency (str | None)
            An EMPTY list is a complete answer: this system carries no instrument under
            that name.

    Raises:
        UpstreamUnavailableError: Service unreachable. Say the instrument could not be
            looked up. NEVER guess a symbol from memory — a wrong symbol silently
            answers a question about a different company, which is exactly the failure
            this tool exists to prevent.

    Constraints:
        - Use the returned `symbol` EXACTLY. Do not shorten it, do not add a suffix, and
          do not invent one for a name that returned nothing.
        - An empty list means "not in this system", NOT "no such company". Say the
          former. The universe is BIST plus the S&P 500 and Nasdaq-100 members, and a
          company outside it is not a company that does not exist.
        - When several instruments come back, they are DIFFERENT companies with similar
          names, not alternatives for the same one. If the user's intent is ambiguous,
          ask which one rather than picking the first.
        - Do NOT present this list to the user as a recommendation, a screen, or a
          shortlist. It is a lookup result, and reading it out as "here are some
          companies you could look at" turns a dictionary entry into advice.
        - Do NOT report the lookup itself to the user. They asked about a company, not
          about how you found its code. Resolve, then answer the actual question.
        - The `market` field says which venue the instrument trades on, not which index
          it belongs to. AAPL is NASDAQ and also an S&P 500 member; the two are
          different facts and this tool only carries the first.
    """
    text = (query or "").strip()
    if len(text) < MIN_QUERY_LENGTH:
        # Tek harf her şeye benziyor. Backend de reddederdi; burada
        # reddetmek bir gidiş-dönüşü ve anlamsız bir hata metnini önlüyor.
        raise ContractViolationError(
            f"{TOOL}: query must be at least {MIN_QUERY_LENGTH} characters."
        )

    wanted = MIN_LIMIT if limit is None else limit
    payload = await backend_client.request(
        "GET",
        "/market/search",
        tool=TOOL,
        # `/market/search` bir DİZİ döndürüyor. Nesneye sarmak arayüzü
        # bozardı: aynı ucu `InstrumentSuggestion[]` olarak okuyan bir
        # "yazdıkça öneri" kutusu var.
        allow_list=True,
        params={
            "q": text,
            "limit": min(
                BACKEND_MAX_LIMIT,
                max(MIN_LIMIT, min(MAX_LIMIT, DEFAULT_LIMIT if limit is None else wanted)),
            ),
        },
    )
    return {"query": text, "instruments": _normalize(payload)}


def _normalize(payload: list[Any]) -> list[dict[str, Any]]:
    """Project the backend's suggestion list onto the v2.19 payload.

    The list-ness itself is enforced by `backend_client` via `allow_list`, so
    there is no second check here -- two guards for one condition means one of
    them is unreachable and the coverage gate would say so.
    """
    return [_normalize_row(row) for row in payload]


def _normalize_row(raw: Any) -> dict[str, Any]:
    """One suggestion.

    `symbol` is required rather than defaulted: a suggestion without a code
    cannot be passed to any other tool, and an empty string would be passed
    anyway and silently match nothing.
    """
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{TOOL}: each instrument must be an object.")
    backend_client.require(raw, ("symbol",), TOOL)
    return {
        "symbol": str(raw["symbol"]),
        # Ad yoksa sembolün kendisi: adı olmayan bir enstrüman düşürülmüyor,
        # çünkü aranan şey zaten sembol.
        "name": str(raw.get("name") or raw["symbol"]),
        "market": str(raw["market"]) if raw.get("market") else None,
        "currency": str(raw["currency"]) if raw.get("currency") else None,
    }


def register(mcp: "FastMCP") -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(resolve_instruments)
