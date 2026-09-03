"""`get_cash_flow_summary` — ne kazandığı, ne harcadığı, geriye ne kaldığı.

Sözleşme v2.16'da eklendi. Yeni veri TOPLAMIYOR: `income_total` ve
`spending_by_category` backend'de zaten vardı ve `GET /banking/spending`
üzerinden arayüze veriliyordu. Eksik olan tek şey ajanın onu GÖREBİLMESİYDİ.

Ölçüldü: "ayda ne kadar yatırım yapabilirim" ve "gelirim giderim ne durumda"
sorularının ikisi de EDUCATION_AGENT'a gidiyor, hiçbir araç çağrılmıyor ve
cevap "Bu bilgi şu anda mevcut değil." oluyordu -- oysa o kullanıcıların
veritabanında üç aylık maaş ve doksan harcama kaydı duruyordu.

Bu, portföyle nakit akışı arasındaki KÖPRÜ. `get_portfolio_positions` neye
sahip olduğunu söylüyor; bu, ne kadarını ayırabildiğini. İkisi aynı ajanda
olmadan "bu alımı kaldırabilir miyim" sorusu cevaplanamıyor.
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

import backend_client
from backend_client import ContractViolationError

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

TOOL = "get_cash_flow_summary"

#: Pencerenin alt sınırı. Otuz günden kısası bir maaş döngüsünü bile
#: kapsamayabiliyor ve o pencerede gelir sıfır görünüyor -- ölçüldü.
MIN_DAYS = 7
MAX_DAYS = 365

_CATEGORY_FIELDS = ("category", "amount", "monthly_amount", "share_percent")

_TOP_LEVEL = (
    "has_data", "coverage_note", "period_days", "months_observed", "currency_code",
    "income_total", "income_events", "expense_total", "net_total",
    "monthly_income", "monthly_expense", "monthly_net",
    "first_transaction_at", "last_transaction_at",
)


async def get_cash_flow_summary(
    user_id: str,
    days: Optional[int] = None,
) -> dict[str, Any]:
    """
    Retrieves what the user EARNED, what they SPENT and what was left over across a
    window, from their bank records. READ-ONLY. This is the only source for the
    user's income and expenses; never infer either from conversation.

    WHEN TO USE
        - "Ayda ne kadar yatırım yapabilirim", "ne kadar biriktirebiliyorum",
          "gelirim giderim ne durumda", "en çok neye harcıyorum",
          "kira giderim ne kadar".
        - Any question about whether the user can AFFORD something: the answer needs
          what is left over each month, not what they already own.

    WHEN NOT TO USE
        - What the user OWNS. That is get_portfolio_positions; a holding is not
          income and a portfolio value is not a budget.
        - Their risk tolerance. That is get_risk_profile_summary.
        - Account balances for a specific transfer or payment.

    Args:
        user_id (str): The authenticated user, from the session envelope. Never a
            value the user typed.
        days (int | None): Window length, 7..365. Default None uses the backend's
            90 days. Do NOT narrow this to 30 without being asked: salary arrives
            monthly, so a 30-day window can contain NO salary at all. Measured on a
            user with three months of salary history — a 30-day window reported
            0 TRY income beside 6.697 TRY of spending.

    Returns:
        dict with exactly these top-level keys:
            coverage_note (str | null): a ready sentence to relay verbatim when
                present, explaining why the monthly average may understate. Null
                when the window covers the income cycle.
            has_data (bool): Whether this user has ANY bank records. False means the
                system holds no banking history for them — NOT that they earn and
                spend nothing. Measured: 3 of 23 users have any. When False every
                amount below is null.
            period_days (int), months_observed (float), currency_code (str)
            income_total, expense_total, net_total (float | null): over the window.
            income_events (int): how many incoming payments landed in the window.
                READ THIS BEFORE REPORTING A ZERO INCOME. Zero income with zero
                events means "nothing arrived in this window"; it does NOT mean the
                person has no income, and saying so is a false statement about
                someone's salary.
            monthly_income, monthly_expense, monthly_net (float | null): the window
                averaged to a month, computed by the backend. Do not divide anything
                yourself; the arithmetic is done in one place so it can be checked.
            categories (list[dict]): what the money went on, largest first, each with
                category, amount, monthly_amount and share_percent (share of total
                SPENDING, not of income).
            first_transaction_at, last_transaction_at (str | null): the observed
                range, so a window wider than the history is visible as such.

    Raises:
        InvalidInputError: `days` outside 7..365.
        UpstreamUnavailableError: Service unreachable. Say the figures could not be
            retrieved. NEVER estimate someone's income or spending from memory or
            from what they mentioned in conversation.

    Constraints:
        - `coverage_note` is a ready Turkish sentence from the backend. When it is
          not null, RELAY IT AS GIVEN alongside the monthly figures. It says why the
          average may sit below what the person actually earns: when `income_events`
          is fewer than `months_observed` the average is UNDERSTATED. Measured — two
          salary payments of 62.000 TRY across a 90-day window average to 41.333
          TRY/month, a third below what the person earns, and it reads as their
          income without the sentence. The rule was written into the prompt first
          and the model did not follow it, which is why the sentence is computed
          rather than requested.
        - `monthly_net` is what was LEFT OVER, measured. It is NOT a recommended
          investment amount and must never be presented as one. Report the figure and
          let the user decide what to do with it; turning "you had 14.985 TRY left
          over" into "you should invest 14.985 TRY" is investment advice this product
          does not give.
        - Do not tell the user to cut a spending category. A rent share of 41% is a
          fact about their budget, not a problem you were asked to solve.
        - PAST WINDOW, NOT A FORECAST. Do not project next month's savings, and do
          not call two months a trend.
        - Always name the window ("son 90 günde") next to any figure. The same person
          has a different answer over 30 and 90 days, and the reader cannot see which
          one they were given.
        - `has_data: false` is a COMPLETE answer: say the system holds no banking
          records for them. It is not an outage and not a zero.
        - Any response containing these figures MUST pass validate_compliance_rules
          before emission.
    """
    if days is not None and not (MIN_DAYS <= int(days) <= MAX_DAYS):
        raise backend_client.InvalidInputError(
            f"{TOOL}: days {days} aralık dışı; {MIN_DAYS}..{MAX_DAYS} bekleniyor."
        )

    payload = await backend_client.request(
        "GET",
        f"/banking/cash-flow/{user_id}",
        tool=TOOL,
        params={} if days is None else {"days": int(days)},
    )
    backend_client.require(payload, ("has_data", "period_days"), TOOL)
    categories = backend_client.require_list(payload, "categories", TOOL)
    return {
        **{field: payload.get(field) for field in _TOP_LEVEL},
        "categories": [_normalize_category(row) for row in categories],
    }


def _normalize_category(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{TOOL}: each category must be an object.")
    backend_client.require(raw, ("category", "amount"), TOOL)
    return {field: raw.get(field) for field in _CATEGORY_FIELDS}


def register(mcp: "FastMCP") -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_cash_flow_summary)
