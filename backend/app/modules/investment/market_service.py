"""Market data reads and writes.

Lives in `investment` because that module owns `investment_products`,
`market_quotes` and `market_candles`. Other modules call these functions
rather than importing the model classes — the boundary rule in CLAUDE.md is
about not sharing ORM classes across modules, not about never talking.
"""

import difflib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import false, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import (
    InstrumentFundamentals,
    InvestmentAccount,
    InvestmentProduct,
    MarketCandle,
    MarketQuote,
    PortfolioPosition,
    WatchlistItem,
)

log = logging.getLogger("moneyfast.market_data")

#: Beyond this, a quote is not "delayed", it is stale — the market moved on
#: and nobody ingested. Both are disclosed, but only one is normal.
STALE_AFTER_MINUTES = 60

#: The provider's own feed delay, in minutes. BIST quotes on the free tier are
#: delayed by roughly this much, and we cannot observe the true tick time — so
#: it is declared as a floor rather than pretended away.
PROVIDER_DELAY_FLOOR_MINUTES = 15


class UnknownSortError(ValueError):
    """An unrecognised `sort_by` reached the query builder.

    Raised rather than defaulted. A caller that asked to rank by daily change
    and silently received alphabetical order has no way to notice, and the
    ranking it presents to the user is wrong without saying so.
    """

    def __init__(self, sort_by: str, allowed: list[str]) -> None:
        self.sort_by = sort_by
        self.allowed = allowed
        super().__init__(
            f"Bilinmeyen sıralama: {sort_by!r}. Geçerli değerler: {', '.join(allowed)}."
        )


def get_product(db: Session, symbol: str) -> Optional[InvestmentProduct]:
    """Exact match on the canonical symbol. Use resolve_symbol for user input."""
    return db.query(InvestmentProduct).filter(InvestmentProduct.symbol == symbol).first()


#: Everyday names for instruments whose ticker nobody types.
#:
#: "XAU" is the ISO code for gold and the obvious thing to type, but the
#: product is XAUUSD named "Altın (Ons/USD)" — so exact match, provider symbol
#: and name substring all miss, and the request died silently returning zero
#: rows. Same for "dolar", which is how people ask for USDTRY.
#:
#: Keys are folded (see `_fold`): case, Turkish dotless-i and accents are
#: normalised in Python rather than left to Postgres `upper()`, because the two
#: disagree on ı/İ and the answer would then depend on the database collation.
_ALIASES = {
    "xau": "XAUUSD", "altin": "XAUUSD", "gold": "XAUUSD", "ons": "XAUUSD",
    "gram altin": "XAUUSD", "ons altin": "XAUUSD",
    "dolar": "USDTRY", "usd": "USDTRY", "amerikan dolari": "USDTRY",
    "dolar kuru": "USDTRY", "usdtry": "USDTRY",
    "euro": "EURTRY", "eur": "EURTRY", "avro": "EURTRY",
    "bist": "XU100", "bist100": "XU100", "bist 100": "XU100",
    "endeks": "XU100",
}


def _fold(text: str) -> str:
    """Casefold with Turkish dotless-i and common accents normalised.

    Done in Python, not via SQL `upper()`: Postgres folds ı/İ differently
    depending on the database collation, so a name lookup that worked in
    development could silently stop matching in production.
    """
    # Every i-shaped letter collapses to plain "i". Mapping "I" to "ı" instead
    # would leave "ALTIN" and "altın" folding to different strings, because
    # translate runs in a single pass and would not fold the result again.
    table = str.maketrans({
        "İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
        "Ü": "u", "ü": "u", "Ö": "o", "ö": "o", "Ç": "c", "ç": "c", "Â": "a", "â": "a",
    })
    return text.translate(table).lower().strip()


#: Words that carry no identity. Dropped before an acronym is built, so
#: "Türk Hava Yolları A.O." yields THY rather than THYAO's unrelated THYA.
_NAME_STOPWORDS = frozenset({
    "as", "ao", "ve", "anonim", "sirketi", "sti", "holding", "inc", "corp",
    "corporation", "co", "plc", "ltd", "limited", "group", "the", "company",
    "sanayi", "ticaret",
})

#: A neighbour must be this close before it is returned without asking, and
#: this far clear of the runner-up. Both conditions, because "one strong
#: match" and "no plausible rival" are different claims and a ticker mix-up
#: is expensive.
_FUZZY_ACCEPT = 0.85
_FUZZY_MARGIN = 0.08

#: A slightly weaker match still settles it when nothing else is close.
#: Measured: "THAYO" scores 0.80 against THYAO with the runner-up 0.13 behind
#: -- one obvious winner. "koz" scores 0.75 against KOZAL and KOZAA with a
#: margin of 0.00, and must ask. The margin is what separates them.
_FUZZY_ACCEPT_CLEAR = 0.78
_FUZZY_MARGIN_CLEAR = 0.12

#: Below this a suggestion is noise rather than help.
_FUZZY_SUGGEST = 0.6


def _acronym(name: str) -> str:
    """Initials of the words that identify a company.

    "Türk Hava Yolları A.O." -> "thy", which is what people actually type and
    what the model emits. Returns "" for single-word names: "Airbnb, Inc."
    would otherwise yield "a" and match almost anything.
    """
    words = [w for w in re.split(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü]+", _fold(name)) if w]
    words = [w for w in words if w not in _NAME_STOPWORDS]
    if len(words) < 2:
        return ""
    return "".join(w[0] for w in words)


def _trim_symbol(candidate: str) -> str:
    """Strip the provider's decoration from something symbol-shaped."""
    upper = candidate.upper()
    for prefix in ("TEST-",):
        if upper.startswith(prefix):
            upper = upper[len(prefix):]
    for suffix in (".IS", "=X"):
        if upper.endswith(suffix):
            upper = upper[: -len(suffix)]
    return upper


def resolve_candidates(
    db: Session, text: str, *, strict: bool = False
) -> list[InvestmentProduct]:
    """Every instrument a human might have meant, best first.

    One element means it is settled; several mean the caller should ask;
    none means there is nothing close enough to suggest.

    The whole match runs in Python over the ~190-row universe rather than in
    SQL. That is not a shortcut -- `_fold` exists precisely because Postgres
    folds i/İ by collation, so a name lookup pushed into SQL can silently stop
    matching on a differently configured database. Here the Turkish rules are
    ours, and testable.

    Order is load-bearing. Fuzzy matching on symbols alone ranks "apple" ->
    APP (0.75) ABOVE AAPL (0.67); the neighbour search runs last so that the
    name rule has already settled it. Cheap, exact rules first, guesses only
    when nothing else fits.
    """
    candidate = (text or "").strip()
    if not candidate:
        # Whitespace is not a lookup. Falling through would match the entire
        # universe on an empty substring.
        return []

    folded = _fold(candidate)
    products = db.query(InvestmentProduct).all()

    # 1. Everyday names a company name cannot yield: "altın" is not a word in
    #    "Altın (Ons/USD)"'s ticker, and "dolar" is nowhere in USDTRY.
    aliased = _ALIASES.get(folded)
    if aliased is not None:
        hit = [p for p in products if p.symbol.upper() == aliased]
        if hit:
            return hit[:1]

    trimmed = _fold(_trim_symbol(candidate))

    # 2. Exact, on either the canonical or the provider symbol.
    exact = [p for p in products
             if _fold(p.symbol) == trimmed or _fold(p.data_symbol or "") == folded]
    if exact:
        return exact[:1]

    # 3. Symbol prefix. "thy" -> THYAO. Measured across the live universe:
    #    only 5 of 185 three-letter prefixes are ambiguous, so this settles
    #    far more often than it asks.
    prefix = [p for p in products if _fold(p.symbol).startswith(trimmed)]
    if len(prefix) == 1:
        return prefix

    # 4. The company's initials, for multi-word names.
    acro = [p for p in products if _acronym(p.name or "") == folded]
    if len(acro) == 1:
        return acro

    # 5. Name substring, folded on BOTH sides. This is what makes
    #    "turk hava yollari" work -- the old SQL LIKE compared raw uppercase
    #    and so required the user to type ü and ı correctly.
    named = [p for p in products if folded in _fold(p.name or "")]
    if len(named) == 1:
        return named

    # An ambiguous deterministic match is still a real answer: these are all
    # genuine matches, so hand them back to be asked about rather than
    # discarding them.
    for group in (prefix, acro, named):
        if len(group) > 1:
            return group[:3]

    # 6. Nearest neighbour, for typos: "aselsn", "THAYO", "garantı".
    #    Skipped in strict mode. A misread ticker on a price question is an
    #    annoyance; on a buy order it spends real money on the wrong company,
    #    so the staging path takes deterministic matches only.
    if strict:
        return []

    scored: list[tuple[float, InvestmentProduct]] = []
    for product in products:
        keys = [_fold(product.symbol), _fold(product.name or "")]
        acronym = _acronym(product.name or "")
        if acronym:
            keys.append(acronym)
        best = max(difflib.SequenceMatcher(None, folded, key).ratio() for key in keys)
        if best >= _FUZZY_SUGGEST:
            scored.append((best, product))

    if not scored:
        return []
    scored.sort(key=lambda pair: pair[0], reverse=True)

    top = scored[0][0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    margin = top - runner_up
    if (top >= _FUZZY_ACCEPT and margin >= _FUZZY_MARGIN) or (
        top >= _FUZZY_ACCEPT_CLEAR and margin >= _FUZZY_MARGIN_CLEAR
    ):
        return [scored[0][1]]

    # Not confident enough to answer, but close enough to ask.
    return [product for _, product in scored[:3]]


def resolve_symbol(
    db: Session, text: str, *, strict: bool = False
) -> Optional[InvestmentProduct]:
    """The instrument a human meant, or None when it is not settled.

    People type "thyao", "THYAO.IS", "THY", "türk hava yolları", "turk hava
    yollari" and "TEST-THYAO". Requiring the canonical spelling is how the
    assistant ended up refusing an ordinary buy order for a stock it holds,
    and how "THY kaç para" became "fiyat verisine ulaşamadım".

    Still conservative where it counts: several candidates means None rather
    than a guess. Callers that can ask the user should use
    `resolve_candidates` and offer them.
    """
    found = resolve_candidates(db, text, strict=strict)
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        log.info(
            "ambiguous instrument reference %r -> %s, refusing to guess",
            text, ", ".join(p.symbol for p in found),
        )
    return None


def list_products(db: Session, only_priced: bool = True) -> list[InvestmentProduct]:
    """Products the ingestor should fetch. `data_symbol IS NULL` means the
    instrument has no upstream feed and must not be priced."""
    query = db.query(InvestmentProduct).filter(InvestmentProduct.status == "active")
    if only_priced:
        query = query.filter(InvestmentProduct.data_symbol.isnot(None))
    return query.order_by(InvestmentProduct.symbol).all()


def latest_quotes(db: Session, symbols: Optional[Iterable[str]] = None) -> dict[str, dict[str, Any]]:
    """Current quote per symbol, keyed by product symbol.

    A plain select now: `market_quotes` holds exactly one row per product,
    overwritten each cycle, so there is no per-product maximum to find.
    """
    statement = (
        select(MarketQuote, InvestmentProduct.symbol, InvestmentProduct.currency_code)
        .join(InvestmentProduct, InvestmentProduct.id == MarketQuote.product_id)
    )
    if symbols:
        statement = statement.where(InvestmentProduct.symbol.in_(list(symbols)))

    out: dict[str, dict[str, Any]] = {}
    for quote, symbol, currency in db.execute(statement).all():
        out[symbol] = {
            "price": float(quote.price),
            "change_amount": float(quote.change_amount) if quote.change_amount is not None else None,
            "change_percent": float(quote.change_percent) if quote.change_percent is not None else None,
            "previous_close": float(quote.previous_close) if quote.previous_close is not None else None,
            "volume": quote.volume,
            "currency": currency,
            "market_timestamp": quote.market_timestamp,
            # When we observed this price. Distinct from market_timestamp,
            # which for a daily bar is the trading date rather than a tick.
            "received_at": quote.received_at,
            "source": quote.source,
        }
    return out


def freshness(quotes: dict[str, dict[str, Any]]) -> tuple[Optional[datetime], int, bool]:
    """(as_of, delay_minutes, is_delayed) across a set of quotes.

    `as_of` is when we OBSERVED the price, not the bar's own timestamp.

    That distinction matters and got this wrong once: the quote path requests
    daily bars, and a daily bar is stamped at the start of its trading day.
    Measuring "delay" from that stamp reported a perfectly current price as
    710 minutes stale, because the session had opened eleven hours earlier.
    The bar's close tracks the live price; its timestamp is a date, not a tick
    time.

    Two components make up the disclosed delay:

    * how long ago we observed it (`received_at` to now), and
    * the provider's own feed delay, which we cannot observe and therefore
      declare as a floor.

    The oldest observation in the set wins, because a payload is only as
    current as its least current figure — taking the newest would let one
    fresh instrument vouch for ninety stale ones.
    """
    stamps = [
        q.get("received_at") or q.get("market_timestamp")
        for q in quotes.values()
        if q.get("received_at") or q.get("market_timestamp")
    ]
    if not stamps:
        return None, 0, True

    as_of = min(stamps)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)

    staleness = max(0, int((datetime.now(timezone.utc) - as_of).total_seconds() // 60))
    delay = staleness + PROVIDER_DELAY_FLOOR_MINUTES
    # Always True for this provider: free-tier BIST data is delayed by design,
    # and claiming otherwise would be false in the ordinary case, not the edge.
    return as_of, delay, True


def upsert_quotes(db: Session, rows: list[dict[str, Any]]) -> int:
    """Overwrite the current quote for each product.

    Unknown symbols are skipped, not created: inventing a product from a
    ticker string would let a typo in a feed become a tradable instrument.
    """
    products = {p.symbol: p.id for p in db.query(InvestmentProduct).all()}
    payload = []
    for row in rows:
        product_id = products.get(row["symbol"])
        if product_id is None:
            log.warning("quote for unknown product %s, skipped", row["symbol"])
            continue
        payload.append(
            {
                "id": str(uuid.uuid4()),
                "product_id": product_id,
                "price": row["price"],
                "change_amount": row.get("change_amount"),
                "change_percent": row.get("change_percent"),
                "previous_close": row.get("previous_close"),
                "volume": row.get("volume"),
                "market_timestamp": row["market_timestamp"],
                "received_at": datetime.now(timezone.utc),
                "source": row.get("source", "yfinance"),
            }
        )
    if not payload:
        return 0

    statement = insert(MarketQuote).values(payload)
    statement = statement.on_conflict_do_update(
        constraint="uq_market_quotes_product",
        set_={
            "price": statement.excluded.price,
            "change_amount": statement.excluded.change_amount,
            "change_percent": statement.excluded.change_percent,
            "previous_close": statement.excluded.previous_close,
            "volume": statement.excluded.volume,
            "market_timestamp": statement.excluded.market_timestamp,
            "received_at": statement.excluded.received_at,
            "source": statement.excluded.source,
        },
    )
    db.execute(statement)
    db.commit()
    return len(payload)


def upsert_fundamentals(db: Session, rows: list[dict[str, Any]]) -> int:
    """Refresh valuation ratios. Missing values are written as NULL.

    Never coalesced to zero: a stock with no earnings data must not screen as
    the cheapest name on the list.
    """
    products = {p.symbol: p for p in db.query(InvestmentProduct).all()}
    payload = []
    renamed = 0
    for row in rows:
        product = products.get(row["symbol"])
        if product is None:
            continue
        product_id = product.id

        # Backfill the company name while we have it. 84 of 97 products are
        # stored with name = ticker, which made "Aselsan" unresolvable —
        # 'ASELS' LIKE '%ASELSAN%' is false because the stored name is shorter
        # than what the user typed. Only filled when it is still the ticker,
        # so a curated name is never overwritten by the provider's.
        provider_name = (row.get("name") or "").strip()
        if provider_name and product.name == product.symbol:
            product.name = provider_name
            renamed += 1
        payload.append(
            {
                "id": str(uuid.uuid4()),
                "product_id": product_id,
                "pe_ratio": row.get("pe_ratio"),
                "pb_ratio": row.get("pb_ratio"),
                "market_cap": row.get("market_cap"),
                "dividend_yield": row.get("dividend_yield"),
                "sector": row.get("sector"),
                "industry": row.get("industry"),
                "week52_high": row.get("week52_high"),
                "week52_low": row.get("week52_low"),
                "updated_at": datetime.now(timezone.utc),
            }
        )
    if not payload:
        return 0

    statement = insert(InstrumentFundamentals).values(payload)
    statement = statement.on_conflict_do_update(
        constraint="uq_instrument_fundamentals_product",
        set_={
            key: getattr(statement.excluded, key)
            for key in ("pe_ratio", "pb_ratio", "market_cap", "dividend_yield",
                        "sector", "industry", "week52_high", "week52_low", "updated_at")
        },
    )
    db.execute(statement)
    db.commit()
    if renamed:
        log.info("backfilled %d instrument names", renamed)
    return len(payload)


def upsert_candles(db: Session, rows: list[dict[str, Any]]) -> int:
    """Store OHLCV bars, ignoring ones already held.

    ON CONFLICT DO NOTHING against the (product, interval, timestamp) unique
    constraint is what makes a backfill re-runnable: the ingestor can ask for
    a year of history every night without duplicating a single bar.
    """
    products = {p.symbol: p.id for p in db.query(InvestmentProduct).all()}
    payload = []
    for row in rows:
        product_id = products.get(row["symbol"])
        if product_id is None:
            continue
        payload.append(
            {
                "id": row.get("id") or str(uuid.uuid4()),
                "product_id": product_id,
                "interval": row.get("interval", "1d"),
                "timestamp": row["timestamp"],
                "open_price": row["open"],
                "high_price": row["high"],
                "low_price": row["low"],
                "close_price": row["close"],
                "volume": row.get("volume"),
                "source": row.get("source", "yfinance"),
            }
        )
    if not payload:
        return 0

    statement = insert(MarketCandle).values(payload).on_conflict_do_nothing(
        constraint="uq_market_candles_bar"
    )
    result = db.execute(statement)
    db.commit()
    return result.rowcount or 0


def candle_coverage(db: Session) -> dict[str, dict[str, Any]]:
    """How many daily bars each instrument holds, and the newest one.

    Exists so the ingestor can back-fill history on start-up without asking
    for it blindly. Daily bars used to be a 19:15 cron and nothing else, which
    meant a fresh clone showed empty charts until that evening -- the reason
    the seed data carried 7.5 MB of candles that a service regenerates on its
    own. With this the ingestor fetches only what is thin, so a first boot
    back-fills the whole universe, a restart fetches nothing, and an
    instrument added by a later migration is picked up the next time it runs.

    Every product appears, including ones with no bars at all: "this symbol
    has nothing" is precisely what the caller needs to be told.
    """
    counts = dict(
        db.query(MarketCandle.product_id, func.count(MarketCandle.id))
        .filter(MarketCandle.interval == "1d")
        .group_by(MarketCandle.product_id)
        .all()
    )
    latest = dict(
        db.query(MarketCandle.product_id, func.max(MarketCandle.timestamp))
        .filter(MarketCandle.interval == "1d")
        .group_by(MarketCandle.product_id)
        .all()
    )
    coverage: dict[str, dict[str, Any]] = {}
    for product in db.query(InvestmentProduct).all():
        last = latest.get(product.id)
        coverage[product.symbol] = {
            "bars": counts.get(product.id, 0),
            "last": last.date().isoformat() if last else None,
        }
    return coverage


def candle_closes(db: Session, symbol: str, limit: int = 260) -> list[tuple[datetime, float]]:
    """Closing prices oldest-first, for return-series calculations."""
    product = get_product(db, symbol)
    if product is None:
        return []
    rows = (
        db.query(MarketCandle)
        .filter(MarketCandle.product_id == product.id, MarketCandle.interval == "1d")
        .order_by(MarketCandle.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [(row.timestamp, float(row.close_price)) for row in reversed(rows)]


def symbol_suggestions(db: Session, symbols: Optional[list[str]]) -> list[dict[str, Any]]:
    """For each query that did not settle, what the user might have meant.

    Separate from `list_instruments` so that function keeps returning a plain
    list of rows. The cost is one more pass over ~190 products, which is
    nothing next to being told "bulunamadı" with no idea why.

    An entry with candidates is a question worth asking; an entry without is
    an honest "nothing close to this".
    """
    out: list[dict[str, Any]] = []
    for query in symbols or []:
        if resolve_symbol(db, query) is not None:
            continue
        out.append({
            "query": query,
            "candidates": [p.symbol for p in resolve_candidates(db, query)],
        })
    return out


def list_instruments(
    db: Session,
    symbols: Optional[list[str]] = None,
    filters: Optional[dict[str, Any]] = None,
    limit: int = 20,
    sort_by: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Quotes joined with fundamentals — the screening read.

    Instruments with no quote yet are omitted: an entry with a null price is
    not a screening result, it is a gap, and showing it in a valuation table
    invites the reader to treat the blank as a number.

    Fundamental filters (`max_pe`) exclude rows whose value is NULL rather
    than treating the gap as passing. "P/E below 10" must not silently mean
    "P/E below 10, or unknown".
    """
    filters = filters or {}
    statement = (
        select(InvestmentProduct, MarketQuote, InstrumentFundamentals)
        .join(MarketQuote, MarketQuote.product_id == InvestmentProduct.id)
        .join(
            InstrumentFundamentals,
            InstrumentFundamentals.product_id == InvestmentProduct.id,
            isouter=True,
        )
        .where(InvestmentProduct.status == "active")
    )

    if symbols:
        resolved = [p.symbol for p in (resolve_symbol(db, s) for s in symbols) if p]
        # An unresolvable symbol must not silently widen the query to
        # everything; it yields no rows and the caller reports it.
        #
        # `false()`, not a sentinel string. This used to be `["\x00"]`, which
        # Postgres rejects outright -- "A string literal cannot contain NUL" --
        # so a request where NOTHING resolved answered 500 instead of an empty
        # list. That is precisely the "koz" case: the one query that most needs
        # a helpful answer was the one that crashed.
        statement = (
            statement.where(InvestmentProduct.symbol.in_(resolved))
            if resolved else statement.where(false())
        )
    if filters.get("market"):
        statement = statement.where(InvestmentProduct.market == filters["market"])
    if filters.get("product_type"):
        statement = statement.where(InvestmentProduct.product_type == filters["product_type"])
    if filters.get("sector"):
        statement = statement.where(
            func.upper(InstrumentFundamentals.sector) == str(filters["sector"]).upper()
        )
    if filters.get("max_pe") is not None:
        statement = statement.where(
            InstrumentFundamentals.pe_ratio.isnot(None),
            InstrumentFundamentals.pe_ratio <= filters["max_pe"],
        )
    if filters.get("min_pe") is not None:
        statement = statement.where(
            InstrumentFundamentals.pe_ratio.isnot(None),
            InstrumentFundamentals.pe_ratio >= filters["min_pe"],
        )
    if filters.get("max_pb") is not None:
        statement = statement.where(
            InstrumentFundamentals.pb_ratio.isnot(None),
            InstrumentFundamentals.pb_ratio <= filters["max_pb"],
        )

    ordering = {
        "change_percent": MarketQuote.change_percent.desc(),
        # "En çok düşenler" needs the other direction. Without it the only
        # change-based key ranked risers, so a losers question was answered
        # with gainers -- confidently, and wrongly.
        "change_percent_asc": MarketQuote.change_percent.asc(),
        "market_cap": InstrumentFundamentals.market_cap.desc(),
        "pe_ratio": InstrumentFundamentals.pe_ratio.asc(),
        "symbol": InvestmentProduct.symbol.asc(),
    }
    if sort_by is not None and sort_by not in ordering:
        # Falling back to alphabetical was worse than failing: a caller that
        # asked to rank by change got symbol order and no indication that its
        # sort had been ignored.
        raise UnknownSortError(sort_by, sorted(ordering))
    statement = statement.order_by(ordering[sort_by or "symbol"])
    statement = statement.limit(max(1, min(200, limit)))

    out = []
    for product, quote, fundamentals in db.execute(statement).all():
        out.append(
            {
                "symbol": product.symbol,
                "name": product.name,
                "market": product.market,
                "currency": product.currency_code,
                "price": float(quote.price),
                "change": float(quote.change_amount) if quote.change_amount is not None else None,
                "change_percent": (
                    float(quote.change_percent) if quote.change_percent is not None else None
                ),
                # Stored on every quote row and, until now, projected by
                # nothing: the chat's "Günlük ciro" column could never be
                # anything but "veri yok".
                "volume": quote.volume,
                "market_timestamp": quote.market_timestamp,
                # When we observed the price, as distinct from the bar's own
                # stamp. Daily bars are stamped at the session open, so
                # measuring staleness from market_timestamp reports a current
                # price as twelve hours old — the same mistake `freshness()`
                # used to make.
                "received_at": quote.received_at,
                "pe_ratio": _opt_float(fundamentals, "pe_ratio"),
                "pb_ratio": _opt_float(fundamentals, "pb_ratio"),
                "market_cap": getattr(fundamentals, "market_cap", None),
                "dividend_yield": _opt_float(fundamentals, "dividend_yield"),
                "sector": getattr(fundamentals, "sector", None),
                "week52_high": _opt_float(fundamentals, "week52_high"),
                "week52_low": _opt_float(fundamentals, "week52_low"),
            }
        )
    return out


def _opt_float(row: Any, field: str) -> Optional[float]:
    value = getattr(row, field, None)
    return float(value) if value is not None else None


def holdings(
    db: Session,
    user_id: Optional[str] = None,
    account_number: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Positions joined with their product and current quote.

    Market value, P&L and weight are computed here from the live quote rather
    than read from stored columns. Storing them would let a position show a
    total that no longer equals price x quantity the moment the price moves —
    which is precisely what the old fixtures did.
    """
    owner = account(db, user_id=user_id, account_number=account_number)
    if owner is None:
        return []

    statement = (
        select(PortfolioPosition, InvestmentProduct, MarketQuote, InstrumentFundamentals)
        .join(InvestmentProduct, InvestmentProduct.id == PortfolioPosition.product_id)
        .join(MarketQuote, MarketQuote.product_id == PortfolioPosition.product_id, isouter=True)
        .join(
            InstrumentFundamentals,
            InstrumentFundamentals.product_id == PortfolioPosition.product_id,
            isouter=True,
        )
        .where(PortfolioPosition.investment_account_id == owner.id)
        .order_by(InvestmentProduct.symbol)
    )

    out = []
    for position, product, quote, fundamentals in db.execute(statement).all():
        quantity = float(position.quantity)
        avg_cost = float(position.average_buy_price)
        price = float(quote.price) if quote is not None else None
        previous = (
            float(quote.previous_close)
            if quote is not None and quote.previous_close is not None
            else None
        )
        out.append(
            {
                "symbol": product.symbol,
                "name": product.name,
                "market": product.market,
                "currency": product.currency_code,
                # The risk engine buckets exposure by sector and reported
                # `{"UNCLASSIFIED": 1.0}` for every portfolio -- not because
                # the sector was unknown (90 of 94 instruments have one) but
                # because the positions handed to it never carried the field.
                "sector": getattr(fundamentals, "sector", None),
                # Carried so the MCP contract can report a real asset_class;
                # every position used to be labelled EQUITY, gold included.
                "product_type": product.product_type,
                "quantity": quantity,
                "avg_cost": avg_cost,
                "price": price,
                "previous_close": previous,
                "change_percent": (
                    float(quote.change_percent)
                    if quote is not None and quote.change_percent is not None
                    else None
                ),
                "market_timestamp": quote.market_timestamp if quote is not None else None,
                "opened_at": position.opened_at,
            }
        )
    return out


#: The account anonymous callers resolve to. Public endpoints work without a
#: token, and they need something to read.
DEMO_ACCOUNT_NUMBER = "TR-DEMO-0001"


def account(
    db: Session,
    user_id: Optional[str] = None,
    account_number: Optional[str] = None,
    allow_demo_fallback: bool = True,
) -> Optional[InvestmentAccount]:
    """The caller's investment account.

    Resolved by user first, because cash and holdings are per-user now — a
    single shared account meant one person's purchase spent everybody's money.
    An anonymous caller (no token) falls back to the demo account so the public
    endpoints keep working.

    `allow_demo_fallback=False` is for the paths that MOVE money. Reading the
    demo portfolio when nobody is signed in is harmless; pricing a trade
    against it is not. An expired session named its user "anonymous", matched
    no account, and silently staged against the shared demo balance — so the
    proposal was costed from a portfolio the user did not own.
    """
    query = db.query(InvestmentAccount)
    if account_number is not None:
        return query.filter(InvestmentAccount.account_number == account_number).first()
    if user_id:
        found = query.filter(InvestmentAccount.user_id == user_id).first()
        if found is not None:
            return found
    if not allow_demo_fallback:
        return None
    return query.filter(
        InvestmentAccount.account_number == DEMO_ACCOUNT_NUMBER
    ).first()


def candle_series(db: Session, symbol: str, limit: int = 400) -> list[dict[str, Any]]:
    """Full OHLCV bars, oldest first. Charts need all four prices, not closes."""
    product = get_product(db, symbol)
    if product is None:
        return []
    rows = (
        db.query(MarketCandle)
        .filter(MarketCandle.product_id == product.id, MarketCandle.interval == "1d")
        .order_by(MarketCandle.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "timestamp": row.timestamp,
            "open": float(row.open_price),
            "high": float(row.high_price),
            "low": float(row.low_price),
            "close": float(row.close_price),
            "volume": row.volume,
        }
        for row in reversed(rows)
    ]


def sector_by_symbol(db: Session) -> dict[str, str]:
    """Sector per symbol, for allocation and heatmap breakdowns."""
    statement = (
        select(InvestmentProduct.symbol, InstrumentFundamentals.sector)
        .join(InstrumentFundamentals,
              InstrumentFundamentals.product_id == InvestmentProduct.id)
        .where(InstrumentFundamentals.sector.isnot(None))
    )
    return {symbol: sector for symbol, sector in db.execute(statement).all()}


def dividend_rows(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    """Dividend yields for held instruments.

    Dates are left empty rather than invented: this provider does not publish
    ex-dates, and a wrong one could have someone trade against it.
    """
    held = {row["symbol"] for row in holdings(db)}
    statement = (
        select(
            InvestmentProduct.symbol,
            InstrumentFundamentals.dividend_yield,
            MarketQuote.price,
            InvestmentProduct.currency_code,
        )
        .join(InstrumentFundamentals,
              InstrumentFundamentals.product_id == InvestmentProduct.id)
        .join(MarketQuote, MarketQuote.product_id == InvestmentProduct.id, isouter=True)
        .where(InstrumentFundamentals.dividend_yield.isnot(None))
        .order_by(InstrumentFundamentals.dividend_yield.desc())
        .limit(limit)
    )
    return [
        {
            "symbol": symbol,
            "currency": currency or "TRY",
            "exDate": "",
            "paymentDate": "",
            "amount": round(float(price) * float(yield_) / 100, 4) if price else 0.0,
            "yieldPercent": round(float(yield_), 2),
        }
        for symbol, yield_, price, currency in db.execute(statement).all()
        if symbol in held or not held
    ]


def recent_orders(db: Session, limit: int = 20) -> list[dict[str, Any]]:
    """Confirmed and pending proposals, as the dashboard's order list.

    Only real proposals appear. A fabricated order history would let a user
    believe they had placed something they never did.
    """
    from .models import TransactionProposal

    rows = (
        db.query(TransactionProposal)
        .order_by(TransactionProposal.created_at.desc())
        .limit(limit)
        .all()
    )
    status_tr = {
        "PENDING_USER_CONFIRMATION": "Bekliyor",
        "CONFIRMED": "Gerçekleşti",
        "REJECTED_VALIDATION": "İptal",
        "REQUIRES_ADDITIONAL_INPUT": "İptal",
    }
    out = []
    for row in rows:
        estimate = (row.payload or {}).get("estimate") or {}
        price = estimate.get("reference_price") or 0.0
        quantity = float(row.quantity or 0)
        out.append(
            {
                "id": row.id,
                "symbol": row.symbol or "-",
                # The currency the order was priced in, from the proposal
                # itself — an order's currency is fixed at staging time and
                # must not be re-read from today's product row.
                "currency": estimate.get("currency") or "TRY",
                "status": status_tr.get(row.status, "Bekliyor"),
                "type": "Alış" if row.transaction_type.upper() in {"BUY", "ALIS", "ALIŞ"} else "Satış",
                "quantity": quantity,
                "price": round(float(price), 4),
                "total": round(float(price) * quantity, 2),
                "date": row.created_at.isoformat(),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Watchlist
#
# What the endpoint returned before was the first eight priced stocks per
# market, alphabetically: the same list for every user, reflecting nobody's
# choice and unchangeable from the interface.
# ---------------------------------------------------------------------------
def watchlist_symbols(db: Session, user_id: str) -> list[str]:
    """The instruments this user follows, oldest pick first."""
    rows = db.execute(
        select(InvestmentProduct.symbol)
        .join(WatchlistItem, WatchlistItem.product_id == InvestmentProduct.id)
        .where(WatchlistItem.user_id == user_id)
        .order_by(WatchlistItem.created_at)
    ).all()
    return [row[0] for row in rows]


def watchlist_add(db: Session, user_id: str, symbol: str) -> Optional[InvestmentProduct]:
    """Follow an instrument. Idempotent: starring twice is not an error.

    Returns None when the symbol resolves to nothing, so the caller can answer
    404 rather than storing a row pointing at an instrument that does not
    exist.
    """
    product = resolve_symbol(db, symbol)
    if product is None:
        return None

    existing = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == user_id, WatchlistItem.product_id == product.id)
        .first()
    )
    if existing is None:
        db.add(WatchlistItem(user_id=user_id, product_id=product.id))
        db.commit()
    return product


def watchlist_remove(db: Session, user_id: str, symbol: str) -> bool:
    """Unfollow. False when it was not on the list, so the caller can 404."""
    product = resolve_symbol(db, symbol)
    if product is None:
        return False
    deleted = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == user_id, WatchlistItem.product_id == product.id)
        .delete()
    )
    db.commit()
    return bool(deleted)
