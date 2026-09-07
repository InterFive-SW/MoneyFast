"""Keep internal identifiers out of user-facing text.

Measured across 158 assistant replies before this existed: the `source` enum
reached the user 7 times, a raw field name once, and internal keys 9 times.
Real examples, verbatim:

    Veri YFINANCE_DELAYED kaynağından, 17 dk gecikmeli (as_of 2026-08-21 13:32)
    sıralama = günlük yüzde değişim (change_percent) yüksekten düşüğe

The prompt now forbids this, but a prompt is advisory. The crisis-resources
instruction was honoured about half the time, which is why `_keep_crisis`
exists in the graph; this is the same lesson applied to naming. The rule tells
the model what to do, and this makes it true.

Deliberately conservative. It rewrites what it is certain about — a known
enum, a parenthetical whose entire content is an identifier — and leaves
everything else alone. Stripping every underscore-containing token would
mangle ordinary text and, worse, silently edit figures.
"""

from __future__ import annotations

import logging
import re
from typing import Tuple

log = logging.getLogger("moneyfast.sanitize")

#: Provider/source enums the tools emit, and what a person should read instead.
#: Naming the provider adds nothing the user can act on; the delay already
#: says what matters about the data.
#: Chosen to fit the sentence they appear in. The observed pattern is
#: "Veri X kaynağından, 17 dk gecikmeli", so a replacement containing
#: "gecikmeli" would read "gecikmeli ... gecikmeli".
SOURCE_REPLACEMENTS = {
    "YFINANCE_DELAYED": "sağlayıcı",
    "YFINANCE": "sağlayıcı",
    "MONEYFAST_FIXTURE_ANALYTICS": "dahili analiz",
    # Alignment enums, from the risk profile summary. Same failure mode as a
    # source enum -- "durumunuz PORTFOLIO_RISKIER" is a database row, not an
    # answer -- but these need a MEANING rather than a category name, because
    # the enum IS the finding. The tool also returns a ready-made Turkish
    # sentence; these replacements are what happens when the model composes
    # its own instead.
    "PORTFOLIO_RISKIER": "beyan ettiğiniz bandın üzerinde",
    "PORTFOLIO_CALMER": "beyan ettiğiniz bandın altında",
    "ALIGNED": "beyan ettiğiniz bandla aynı",
}

#: Envelope and payload keys that describe the plumbing rather than the value.
#: Only these exact words are removed, and only where they appear as an
#: identifier — see `_IDENT` below.
INTERNAL_KEYS = (
    "as_of", "is_delayed", "delay_minutes", "index_lag_minutes",
    "change_percent", "change_percent_asc", "market_cap", "pe_ratio", "pb_ratio",
    "dividend_yield", "week52_high", "week52_low", "market_value", "cost_basis",
    "unrealized_pnl", "unrealized_pnl_pct", "available_quantity", "avg_cost",
    "instrument_currency", "base_currency", "asset_class", "product_type",
    "source_account_id", "destination_account_id", "idempotency_key",
    "proposal_id", "user_id", "trace_id", "top_k", "min_similarity",
    # v2.21. `lean` bir SIRALAMA büyüklüğü ve kullanıcıya hiçbir şey
    # söylemiyor; ölçüldü, model onu "(lean -%0,017)" diye cevabın içine
    # yazdı. Araç sözleşmesi bunu açıkça yasaklıyor ve prompt tavsiye olduğu
    # için kural burada da duruyor. `sources_measured` ve `evidence_count`
    # aynı sınıftan: okumanın muhasebesi, okumanın kendisi değil.
    "lean", "sources_measured", "evidence_count", "horizon_note",
    "by_source", "up_lean", "down_lean",
    "max_weight", "order_type", "time_in_force", "price_history",
    "market_corpus", "valuation_mode", "rebalance_assumption", "confidence_level",
    # Risk profile summary (v2.4). `measured_level` and `declared_tolerance`
    # name the two halves of the one comparison this product is allowed to
    # make, so they are the likeliest of these to be written out verbatim.
    "profile_summary", "measured_level", "declared_tolerance", "alignment",
    "tolerance_level", "investment_horizon", "questionnaire_version",
    "position_count", "effective_n", "top_3_weight", "largest_position",
    "volatility_annualized", "risk_free_rate", "observation_count",
    "data_quality", "is_statistically_reliable", "excluded_symbols",
    "gap_filled_days",
    # Technical signals (v2.10). `rsi_14` and `sma_50` are the likeliest of
    # these to be written out verbatim -- they read like names rather than
    # keys, and the model has no way to know they are ours.
    "sma_20", "sma_50", "sma_200", "rsi_14",
    "pct_from_sma_20", "pct_from_sma_50", "pct_from_sma_200",
    "week52_position_pct", "up_days_recent", "recent_window",
    "volume_vs_average", "max_drawdown_pct", "annualised_volatility",
    "last_close", "observations", "narrative",
)

#: An identifier standing on its own, not part of a longer word.
_IDENT = re.compile(r"(?<![\w])(" + "|".join(map(re.escape, INTERNAL_KEYS)) + r")(?![\w])")

#: A parenthetical whose whole content is an identifier, optionally followed by
#: a value: "(change_percent)", "(as_of 2026-08-21 13:32)". Removed entirely —
#: deleting only the token would leave "( 2026-08-21 13:32)".
_PAREN = re.compile(
    r"\s*[（(]\s*(?:" + "|".join(map(re.escape, INTERNAL_KEYS)) + r")\b[^)）]*[)）]"
)


def sanitize(text: str) -> Tuple[str, list[str]]:
    """Return cleaned text and the identifiers that had to be removed.

    The list is what makes this measurable: an empty list every turn means the
    prompt is doing its job, and a non-empty one says which rule the model is
    ignoring.
    """
    if not text:
        return text, []

    found: list[str] = []

    for enum, replacement in SOURCE_REPLACEMENTS.items():
        if enum in text:
            found.append(enum)
            text = text.replace(enum, replacement)

    # `_PAREN` only matches when an identifier is present, so findall always
    # yields at least one; guarding for the empty case would be a branch that
    # cannot be reached or tested.
    for match in _PAREN.finditer(text):
        found.extend(_IDENT.findall(match.group(0)))
    text = _PAREN.sub("", text)

    # Anything left standing outside a parenthetical: drop the identifier and
    # the punctuation that introduced it, so "sıralama = change_percent" does
    # not become "sıralama = ".
    for match in _IDENT.finditer(text):
        found.append(match.group(1))
    text = _IDENT.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"(?m)[ \t]+$", "", text)

    return text, found


def sanitized(text: str, trace_id: str = "") -> str:
    """`sanitize`, but logging what it caught. Never raises."""
    try:
        cleaned, found = sanitize(text)
    except Exception as exc:  # noqa: BLE001 - a cleaner must not break a turn
        log.warning("sanitize failed, emitting text unchanged: %s", exc)
        return text
    if found:
        log.warning(
            "internal identifiers removed from reply: %s (trace=%s)",
            ", ".join(sorted(set(found))), trace_id or "-",
        )
    return cleaned
