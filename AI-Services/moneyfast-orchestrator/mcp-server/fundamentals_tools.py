"""`get_company_fundamentals` — şirketin işi nasıl gidiyor.

Sözleşme v2.14. Bu araç YENİ VERİ TOPLAMIYOR: `instrument_fundamentals`
tablosu otuz beş alan taşıyor ve 1.011 enstrümanda dolu -- gelir, marjlar,
özkaynak kârlılığı, borç/özkaynak, serbest nakit akışı, hisse başına kâr,
analist konsensüsü. `GET /market/fundamentals` hepsini zaten veriyor ve
yalnızca hisse detay sayfası okuyordu. Ajanın bir şirket hakkında
görebildiği her şey fiyat, günlük değişim, hacim ve dört orandan ibaretti.

`get_market_data`'nın donuk v2.2 şeması DEĞİŞMEDİ. O "bu ne ediyor" sorusunun
cevabı; bu "bu şirketin işi nasıl" ve farklı bir başarısızlık biçimi var:
sağlayıcı bir alanı yayımlamayabiliyor ve evrenin yarısında analist görüşü
hiç yok.

EN ÖNEMLİ SINIR: BU BİR ANLIK GÖRÜNTÜ, SERİ DEĞİL. `updated_at` veriyi ne
zaman ÇEKTİĞİMİZİ söylüyor, hangi döneme ait olduğunu değil. Önceki çeyrek
saklanmıyor. Dolayısıyla bu araçla "son çeyrek kârı şu kadar arttı" gibi bir
cümle kurulamaz -- kıyaslanacak ikinci bir dönem yok. Sözleşme bunu ajana
açıkça söylüyor, çünkü söylemezse model iki dönem varmış gibi yazar.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

import backend_client
from backend_client import ContractViolationError

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

TOOL = "get_company_fundamentals"
QUARTERLY_TOOL = "get_quarterly_financials"

#: Tek çağrıda kaç enstrüman. Ölçüldü: enstrüman başına ~1.030 karakter,
#: dolayısıyla beş sembol ~5.150 ve sentez gövdesinin 8.000 karakterlik
#: bütçesine sığıyor. Altıncısı bütçeyi zorlar ve bu daldan bir kez
#: sağlayıcı sınırını aşmanın ne demek olduğu öğrenildi: kullanıcı her
#: seferinde "yoğunluk sınırına takıldım" cevabı alıyordu.
MAX_SYMBOLS = 5

#: Yanıtta taşınan alanlar. Backend'in verdiğinin TAMAMI değil: `updated_at`
#: dışarıda tutuldu çünkü ajana verilecek bir tarih değil -- veriyi ne zaman
#: çektiğimizi söylüyor ve modelin onu raporlama dönemi sanması, bu aracın
#: yaratabileceği tek ciddi yanlış.
FIELDS = (
    "sector", "industry",
    # Değerleme
    "pe_ratio", "pb_ratio", "forward_pe", "market_cap", "enterprise_value",
    # Gelir ve kârlılık
    "total_revenue", "revenue_growth",
    "gross_margin", "operating_margin", "ebitda_margin", "profit_margin",
    "return_on_equity", "return_on_assets",
    # Bilanço ve nakit
    "debt_to_equity", "current_ratio",
    "total_debt", "total_cash", "free_cash_flow", "operating_cash_flow",
    # Hisse başına
    "trailing_eps", "forward_eps", "earnings_growth",
    # Temettü
    "dividend_yield", "dividend_rate", "payout_ratio", "ex_dividend_date",
    # Piyasa duyarlılığı ve takvim
    "beta", "week52_high", "week52_low", "earnings_date",
    # Analist konsensüsü — üçü BİRLİKTE taşınıyor, bkz. `_normalize`.
    "recommendation_key", "analyst_count", "target_mean_price",
)


async def get_company_fundamentals(symbols: list[str]) -> dict[str, Any]:
    """
    Retrieves the stored financial fundamentals for named instruments: revenue, margins,
    return on equity, debt, cash flow, earnings per share, dividend terms and the
    published analyst consensus. READ-ONLY.

    WHEN TO USE
        - The user asks how a company's BUSINESS is doing rather than what its share
          costs: "AKBNK'ın kâr marjı ne", "THYAO borçlu mu", "ASELS'in özkaynak
          kârlılığı", "bu şirket temettü veriyor mu", "analistler ne diyor".
        - A comparison on business quality: "AKBNK mı GARAN mı daha kârlı".

    WHEN NOT TO USE
        - The current price, daily change or volume. Use get_market_data.
        - Trend, moving averages, momentum. Use get_technical_signals.
        - Anything about the user's own holdings. Use get_portfolio_positions.
        - WHY a figure is what it is, or what commentators say about it. Use
          rag_semantic_market_search.

    Args:
        symbols (list[str]): 1..5 instrument symbols, e.g. ["AKBNK", "THYAO"]. More
            than five are refused rather than truncated: a silently dropped symbol
            would be answered as though it had been looked at.

    Returns:
        dict with exactly these top-level keys:
            instruments (list[dict]): one per symbol found, each carrying
                symbol, name, currency, and `fundamentals` — every field below, any
                of which may be null:
                sector, industry, pe_ratio, pb_ratio, forward_pe, market_cap,
                enterprise_value, total_revenue, revenue_growth, gross_margin,
                operating_margin, ebitda_margin, profit_margin, return_on_equity,
                return_on_assets, debt_to_equity, current_ratio, total_debt,
                total_cash, free_cash_flow, operating_cash_flow, trailing_eps,
                forward_eps, earnings_growth, dividend_yield, dividend_rate,
                payout_ratio, ex_dividend_date, beta, week52_high, week52_low,
                earnings_date, recommendation_key, analyst_count, target_mean_price.
            not_found (list[str]): symbols that resolved to no instrument.
            missing_data (list[str]): symbols that resolved but hold no fundamentals
                at all. Distinct from not_found: the instrument exists, the figures
                do not.

    Raises:
        InvalidInputError: No symbol given, or more than five. Correct and retry.
        UpstreamUnavailableError: Service unreachable. Say the figures could not be
            retrieved. NEVER answer from memory — a remembered margin for a real
            company is the most convincing kind of wrong answer.

    Constraints:
        - THIS IS A SNAPSHOT, NOT A SERIES. The system stores one current value per
          field and no history. You therefore CANNOT say "son çeyrek", "bu çeyrek",
          "geçen yıla göre", "arttı", "düştü" or anything else that compares two
          periods — there is no second period to compare against. State the figure as
          the latest stored value and nothing more.
        - `revenue_growth` and `earnings_growth` are the provider's OWN single ratios
          and the period they span is NOT stored. Never label them with a period and
          never call them a forecast: not "son çeyrek", not "gelecek yıl", not
          "tahmin ediliyor". Measured: the model reported earnings growth as "gelecek
          yıl için tahmin ediliyor" — a claim the data does not make.
        - `forward_pe` and `forward_eps` ARE the provider's forward estimates and are
          the ONLY two fields you may describe that way. Attribute them ("sağlayıcının
          ileriye dönük tahmini"); they are not this system's expectation.
        - A null field means the provider does not publish it for this instrument,
          NOT zero and NOT unavailable-right-now. Measured: 979 of 1.011 instruments
          have a profit margin, 892 have debt-to-equity, and only 484 have an analyst
          view. Say "veri yok"; never print 0.
        - Do NOT name the fields by their keys. "kâr marjı", not "profit_margin";
          "özkaynak kârlılığı", not "return_on_equity".
        - Analyst consensus travels as three values and must be REPORTED as three:
          the recommendation, how many analysts, and the mean target. A target price
          without the count is a number with no author. Reporting that analysts
          published a view is permitted; endorsing it, averaging it into your own
          view, or presenting it as this system's expectation is not — and the target
          is THEIRS, never a price target this product produces.
        - Do NOT convert any figure into a verdict on the share: a high margin is not
          a reason to buy and a high debt ratio is not a reason to sell.
        - Any response containing these figures MUST pass validate_compliance_rules
          before emission.
    """
    wanted = [str(symbol).strip().upper() for symbol in (symbols or []) if str(symbol).strip()]
    if not wanted:
        raise backend_client.InvalidInputError(f"{TOOL}: en az bir sembol gerekiyor.")
    if len(wanted) > MAX_SYMBOLS:
        # Kırpmak yerine reddediliyor: sessizce düşen bir sembol, bakılmış
        # gibi cevaplanır ve kullanıcı hangisinin düştüğünü bilemez.
        raise backend_client.InvalidInputError(
            f"{TOOL}: tek çağrıda en fazla {MAX_SYMBOLS} sembol; {len(wanted)} verildi."
        )

    instruments: list[dict[str, Any]] = []
    not_found: list[str] = []
    missing_data: list[str] = []

    # Uç nokta tek sembol alıyor, dolayısıyla sembol başına bir istek. Beş
    # yerel çağrı, toplu bir uç eklemekten ucuz: bu faz var olan veriyi
    # erişilebilir kılıyor, backend'e yeni yüzey açmıyor.
    for symbol in wanted:
        payload = await backend_client.request(
            "GET", "/market/fundamentals", tool=TOOL, params={"symbol": symbol}
        )
        row = _normalize(payload, symbol)
        if row is None:
            not_found.append(symbol)
        elif not any(row["fundamentals"][field] is not None for field in FIELDS):
            # Enstrüman var, rakamları yok. `not_found`'dan AYRI: biri "böyle
            # bir şirket yok", diğeri "şirket var, verisi henüz çekilmemiş" --
            # ve ajanın kullanıcıya söyleyeceği cümle ikisinde farklı.
            missing_data.append(symbol)
        else:
            instruments.append(row)

    return {
        "instruments": instruments,
        "not_found": not_found,
        "missing_data": missing_data,
    }


def _normalize(payload: Any, requested: str) -> Optional[dict[str, Any]]:
    """Backend yanıtını v2.14 gövdesine indirger.

    Bulunamayan sembol için backend `{"symbol": ...}` döndürüyor, hata değil.
    Burada None'a çevriliyor ki çağıran onu `not_found`'a koyabilsin.
    """
    backend_client.require(payload, ("symbol",), TOOL)
    if "name" not in payload:
        return None
    return {
        "symbol": str(payload["symbol"]),
        "name": str(payload.get("name") or requested),
        "currency": str(payload.get("currency") or "TRY"),
        # Eksik alan ANAHTAR olarak kalıyor, değeri None. Anahtarı düşürmek,
        # `fundamentals["profit_margin"]` okuyan bir tüketiciye KeyError
        # verirdi; None ise "sağlayıcı bunu yayımlamıyor" diyor.
        "fundamentals": {field: payload.get(field) for field in FIELDS},
    }


async def get_quarterly_financials(symbol: str) -> dict[str, Any]:
    """
    Retrieves one instrument's QUARTERLY income statement, period by period: revenue,
    net income, pre-tax income and operating expense, newest quarter first. READ-ONLY.

    This is the series that `get_company_fundamentals` does not have. That tool stores
    one current value per field with no history; this one stores each quarter
    separately, and it is the only way to say what a company earned in a named quarter
    or how that compares with another quarter.

    WHEN TO USE
        - The user asks about a named period: "AKBNK'ın son çeyrek kârı ne kadar",
          "geçen çeyreğe göre ne oldu", "2026'nın ilk çeyreğinde ne kazandı",
          "geçen yılın aynı çeyreğiyle kıyasla".
        - Any question whose answer needs two periods.

    WHEN NOT TO USE
        - Ratios, margins, debt, analyst consensus. Those are
          get_company_fundamentals; they are not stored per quarter.
        - Price, trend, or the user's own holdings.

    Args:
        symbol (str): ONE instrument symbol. Exactly one: a quarter-by-quarter answer
            is already several numbers, and two instruments at once produce a table
            nobody reads.

    Returns:
        dict with exactly these top-level keys:
            symbol (str), name (str), currency (str)
            periods (list[dict]): newest first, each with
                period_end (str, ISO date), label (str, e.g. "2026Q2"),
                total_revenue, net_income, pretax_income, operating_expense —
                any figure may be null.
            previous_is_adjacent (bool): whether the second entry is the quarter
                IMMEDIATELY before the first. Measured: the provider skips quarters —
                3 of 40 sampled BIST instruments have no 2025Q3 income statement at
                all. When this is false the two newest entries are NOT consecutive.
            year_ago_available (bool): whether the same quarter one year earlier is
                in the series.

    Raises:
        InvalidInputError: No symbol given.
        UpstreamUnavailableError: Service unreachable. Say the figures could not be
            retrieved; never recall a quarter from memory.

    Constraints:
        - NAME THE PERIOD in every figure you report. "2026Q2'de 15,2 milyar TL net
          kâr", never "son çeyrekte 15,2 milyar" without saying which quarter. The
          series has holes and the reader cannot see them.
        - Compare the two newest quarters ONLY when `previous_is_adjacent` is true.
          When it is false, say the intervening quarter is not available and compare
          nothing — a comparison across a gap reads as quarter-over-quarter and is
          not. Measured: without this rule the answer would silently put 2025Q2 next
          to 2025Q4 for three instruments in forty.
        - Compare with the year-ago quarter ONLY when `year_ago_available` is true.
        - An empty `periods` list means this system holds no quarterly data for the
          instrument. Measured: 6 of 40 sampled instruments have none. Say exactly
          that; it is not an outage and not a zero.
        - A null figure means the provider did not publish that line for that quarter,
          NOT zero. 16 of 34 instruments with data have a hole somewhere in the series.
        - Write every comparison in CHRONOLOGICAL order -- older quarter first, newest
          second: "2026Q1 19,2 milyar TL -> 2026Q2 15,2 milyar TL". The series arrives
          NEWEST FIRST and relaying it in arrival order points the arrow the opposite
          way to the change being described. Measured: "%-20,7 azalma (15,2 milyar TL
          -> 19,2 milyar TL)" -- the sentence says a fall, the arrow shows a rise.
        - These are REPORTED PAST RESULTS. Do not extrapolate the next quarter, do not
          call a rise a trend, and do not turn any of it into a view on the share.
        - Do NOT name the fields by their keys: "net kâr", not "net_income".
        - Any response containing these figures MUST pass validate_compliance_rules.
    """
    wanted = str(symbol or "").strip().upper()
    if not wanted:
        raise backend_client.InvalidInputError(f"{QUARTERLY_TOOL}: bir sembol gerekiyor.")

    payload = await backend_client.request(
        "GET", "/market/quarterly", tool=QUARTERLY_TOOL, params={"symbol": wanted}
    )
    backend_client.require(payload, ("symbol", "periods"), QUARTERLY_TOOL)
    periods = backend_client.require_list(payload, "periods", QUARTERLY_TOOL)
    return {
        "symbol": str(payload["symbol"]),
        "name": str(payload.get("name") or wanted),
        "currency": str(payload.get("currency") or "TRY"),
        "periods": [_normalize_period(row) for row in periods],
        # Sunucudan geliyor, BURADA hesaplanmıyor: kural tek yerde durmalı,
        # yoksa her tüketici aynı boşluğu ayrı ayrı gözden kaçırır.
        "previous_is_adjacent": bool(payload.get("previous_is_adjacent", False)),
        "year_ago_available": bool(payload.get("year_ago_available", False)),
    }


_QUARTER_FIELDS = (
    "total_revenue", "net_income", "pretax_income", "operating_expense",
)


def _normalize_period(raw: Any) -> dict[str, Any]:
    """Bir çeyrek. Etiket ZORUNLU: dönemi adlandırmadan rakam vermek, serinin
    deliklerini okunamaz kılar."""
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{QUARTERLY_TOOL}: each period must be an object.")
    backend_client.require(raw, ("period_end", "label"), QUARTERLY_TOOL)
    return {
        "period_end": str(raw["period_end"]),
        "label": str(raw["label"]),
        **{field: raw.get(field) for field in _QUARTER_FIELDS},
    }

def register(mcp: "FastMCP") -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_company_fundamentals)
    mcp.tool()(get_quarterly_financials)
