"""Verdict assembly.

The asymmetry throughout this module is deliberate: every ambiguity resolves
toward BLOCK. An unreachable or confused rule engine must cost a user one
reply, not cost the firm a licence.
"""

import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from . import rules

DEFAULT_BLOCK_REASON = (
    "Bu soruya bu şekilde yanıt veremem. Dilerseniz geçmiş verileri ve "
    "maliyetleri birlikte inceleyebiliriz."
)

SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


class UnsupportedJurisdiction(Exception):
    """No rule pack for the requested code. Treated as BLOCK upstream."""


#: A figure that could be read as a financial claim: an amount, a percentage,
#: or a price. Deliberately broad — a false positive costs one extra line of
#: boilerplate, a false negative omits a legally required disclosure.
_FIGURE = re.compile(
    r"(\d[\d.,]*\s*(?:%|tl|try|usd|eur|\$|₺|€|lira|adet|puan)"
    r"|(?:%|\$|₺|€)\s*\d)",
    re.IGNORECASE,
)


#: Routing is recorded as a tool on every single turn, but it only classifies
#: the request -- it reaches no market data and produces no figure. Counting it
#: as financial content would make the disclaimer unconditional again by the
#: back door, which is exactly the behaviour being fixed.
NON_FINANCIAL_TOOLS = frozenset({"classify_and_route_intent"})


def has_financial_content(
    draft: str,
    contains_personal_data: bool,
    contains_transaction_proposal: bool,
    tools_used: List[str],
) -> bool:
    """Whether this draft makes a financial claim at all.

    The general disclaimer used to be attached unconditionally, so a greeting
    and a "I could not reach the data" message both carried three sentences
    about past performance not guaranteeing future returns. Boilerplate under
    text that asserts nothing does not inform anyone; it trains the reader to
    skip the notice on the answers where it matters.

    Note a failed tool call never reaches `tools_used` -- the orchestrator only
    records a tool on success -- so an error message is correctly treated as
    carrying no claim.
    """
    if contains_personal_data or contains_transaction_proposal:
        return True
    if any(tool not in NON_FINANCIAL_TOOLS for tool in tools_used):
        return True
    return bool(_FIGURE.search(draft or ""))


def required_disclosures(
    draft: str,
    contains_personal_data: bool,
    contains_transaction_proposal: bool,
    tools_used: List[str],
) -> List[Dict[str, str]]:
    """Disclosures the draft is missing.

    Presence is tested on the disclosure's own text, so a draft that already
    carries one is not asked to repeat it.
    """
    needed: List[Dict[str, str]] = []

    if has_financial_content(
        draft, contains_personal_data, contains_transaction_proposal, tools_used
    ):
        needed.append(rules.DISCLOSURES["DISC-GENERAL"])

    if contains_personal_data:
        needed.append(rules.DISCLOSURES["DISC-PERSONAL"])
    if contains_transaction_proposal:
        needed.append(rules.DISCLOSURES["DISC-PROPOSAL"])
    # Any tool that carries an is_delayed flag can have produced delayed
    # figures; the orchestrator does not tell us which, so the disclosure is
    # required whenever such a tool contributed. `get_market_data` belongs here
    # for the plainest reason of all: it is the tool that returns is_delayed,
    # and a bare price answer was going out with no delay notice at all.
    if any(
        tool in {
            "get_portfolio_positions",
            "rag_semantic_market_search",
            "calculate_portfolio_risk_metrics",
            "get_market_data",
        }
        for tool in tools_used
    ):
        needed.append(rules.DISCLOSURES["DISC-DELAYED"])

    return [entry for entry in needed if entry["text"] not in draft]


def _remediate(draft: str, violations: List[Dict[str, Any]]) -> Optional[str]:
    """Rewrite the non-CRITICAL spans, right to left.

    Right to left because every replacement shifts the offsets of everything
    after it; editing left to right would corrupt the second span onward.

    Returns None when any finding has no safe replacement, which is what makes
    the caller fall through to BLOCK rather than emit a partially cleaned
    draft.
    """
    editable = []
    for violation in violations:
        rule = rules.rule_by_id(violation["rule_id"])
        if rule is None or rule.replacement is None:
            return None
        editable.append((violation["offending_span"], rule.replacement))

    remediated = draft
    for span, replacement in sorted(editable, key=lambda item: item[0]["start"], reverse=True):
        remediated = remediated[: span["start"]] + replacement + remediated[span["end"] :]
    return remediated


def _append_disclosures(text: str, disclosures: List[Dict[str, str]]) -> str:
    """Insert missing disclosures verbatim.

    Verbatim matters: the contract instructs the orchestrator never to
    paraphrase, shorten, translate or merge them, so the remediated draft must
    already contain the exact strings.
    """
    prepend = [entry["text"] for entry in disclosures if entry["placement"] == "PREPEND"]
    append = [entry["text"] for entry in disclosures if entry["placement"] != "PREPEND"]
    parts = prepend + [text] + append
    return "\n\n".join(part for part in parts if part)


def validate(request: Dict[str, Any]) -> Dict[str, Any]:
    jurisdiction = str(request.get("jurisdiction", "TR")).upper()
    if jurisdiction not in rules.SUPPORTED_JURISDICTIONS:
        # No permissive fallback. An unknown jurisdiction means the applicable
        # rules are unknown, which is not the same as there being none.
        raise UnsupportedJurisdiction(jurisdiction)

    draft = request["draft_response"]
    violations = rules.find_violations(
        draft,
        strictness=request.get("strictness", "STANDARD"),
        contains_personal_data=bool(request.get("contains_personal_data")),
    )
    disclosures = required_disclosures(
        draft,
        bool(request.get("contains_personal_data")),
        bool(request.get("contains_transaction_proposal")),
        list(request.get("tools_used") or []),
    )

    audit_id = str(uuid.uuid4())
    critical = [v for v in violations if v["severity"] == "CRITICAL"]

    if critical:
        return {
            "verdict": "BLOCK",
            "rule_pack_version": rules.RULE_PACK_VERSION,
            "violations": violations,
            "required_disclosures": disclosures,
            "remediated_response": None,
            "blocked_reason_user_facing": DEFAULT_BLOCK_REASON,
            "audit_id": audit_id,
        }

    if not violations and not disclosures:
        return {
            "verdict": "PASS",
            "rule_pack_version": rules.RULE_PACK_VERSION,
            "violations": [],
            "required_disclosures": [],
            "remediated_response": None,
            "blocked_reason_user_facing": None,
            "audit_id": audit_id,
        }

    remediated = _remediate(draft, violations)
    if remediated is None:
        # A finding with no safe rewrite. The original draft is never a
        # fallback, so this becomes BLOCK.
        return {
            "verdict": "BLOCK",
            "rule_pack_version": rules.RULE_PACK_VERSION,
            "violations": violations,
            "required_disclosures": disclosures,
            "remediated_response": None,
            "blocked_reason_user_facing": DEFAULT_BLOCK_REASON,
            "audit_id": audit_id,
        }

    return {
        "verdict": "REVISE",
        "rule_pack_version": rules.RULE_PACK_VERSION,
        "violations": violations,
        "required_disclosures": disclosures,
        "remediated_response": _append_disclosures(remediated, disclosures),
        "blocked_reason_user_facing": None,
        "audit_id": audit_id,
    }
