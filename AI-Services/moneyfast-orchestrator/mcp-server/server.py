# filename: server.py
"""MoneyFast MCP server entrypoint.

Creates the shared FastMCP instance and binds every domain module to it.
Each module exposes a `register(mcp)` function; the tool callables stay at
module level so they can be imported and unit-tested without a running
server.

Contracts follow "MCP Tools Interface Definitions v2.2": the six v2.1 tools
are unchanged, get_market_data was added in v2.2, and Phase 2 adds
get_social_market_signals for Market Research social evidence.

Six of the seven tools call a real HTTP service: get_portfolio_positions,
prepare_transaction_proposal, calculate_portfolio_risk_metrics and
validate_compliance_rules reach the backend, and rag_semantic_market_search
reaches the rag service. Only classify_and_route_intent is computed locally,
because routing needs no state. Nothing here falls back to canned data when a
service is unreachable; every failure raises.

Run:
    pip install "mcp[cli]"
    python server.py                 # stdio transport
    mcp dev server.py                # inspector UI
"""

# from __future__ import annotations

import logging

import backend_client
import compliance_tools
import market_data_tools
import market_research_tools
import orchestrator_tools
import portfolio_tools
import risk_strategy_tools
import social_signals_tools
import transaction_tools
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("moneyfast.mcp")

SERVER_NAME = "moneyfast"
CONTRACT_VERSION = "v2.2"

SERVER_INSTRUCTIONS = """\
MoneyFast tool server. Eight tools across research and account domains.

Routing: call classify_and_route_intent first on every user turn.
Data:    get_portfolio_positions, get_market_data,
         rag_semantic_market_search, get_social_market_signals and
         calculate_portfolio_risk_metrics return freshness fields where
         applicable. Propagate them.
Social:  get_social_market_signals is supporting evidence only. Never treat
         unverified posts as official disclosures; prefer kap_url when present.
Prices:  get_market_data is the ONLY source for the price or valuation of an
         instrument the user does not hold. A null fundamental means the
         provider does not publish it; report "veri yok", never 0.
Empty:   an empty list is a valid, complete answer. Never substitute
         remembered or illustrative data for it.
Gate:    validate_compliance_rules runs on every user-facing draft that
         references an instrument, a figure, a market view or a
         transaction. Fail closed.
Staging: prepare_transaction_proposal stages only. Nothing in this server
         executes an order. Confirmation happens in the frontend.
"""

mcp = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS, host="0.0.0.0", port=8000)

DOMAIN_MODULES = (
    ("orchestrator", orchestrator_tools),
    ("portfolio", portfolio_tools),
    ("market_data", market_data_tools),
    ("market_research", market_research_tools),
    ("social_signals", social_signals_tools),
    ("risk_strategy", risk_strategy_tools),
    ("compliance", compliance_tools),
    ("transaction", transaction_tools),
)


def build_server() -> FastMCP:
    """Register every domain module against the shared FastMCP instance."""
    for domain, module in DOMAIN_MODULES:
        module.register(mcp)
        log.info("registered domain: %s (%s)", domain, module.__name__)
    log.info(
        "moneyfast mcp ready, contract %s, backend=%s rag=%s",
        CONTRACT_VERSION,
        backend_client.base_url(),
        backend_client.rag_base_url(),
    )
    return mcp


build_server()


if __name__ == "__main__":
    # SADECE SSE İLE ÇALIŞTIR (host ve port'u sildik)
    mcp.run(transport="sse")
