# filename: server.py
"""MoneyFast MCP server entrypoint.

Creates the shared FastMCP instance and binds every domain module to it.
Each module exposes a `register(mcp)` function; the tool callables stay at
module level so they can be imported and unit-tested without a running
server.

Contracts are frozen against "MCP Tools Interface Definitions v2.1".
Every tool in this build returns deterministic mock data. No network,
database, or broker call is made anywhere in this package.

Run:
    pip install "mcp[cli]"
    python server.py                 # stdio transport
    mcp dev server.py                # inspector UI
"""

#from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

import compliance_tools
import market_research_tools
import orchestrator_tools
import portfolio_tools
import risk_strategy_tools
import transaction_tools
import budget_tools

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("moneyfast.mcp")

SERVER_NAME = "moneyfast"
CONTRACT_VERSION = "v2.1"

SERVER_INSTRUCTIONS = """\
MoneyFast tool server. Seven tools across seven domains.

Routing: call classify_and_route_intent first on every user turn.
Data:    get_portfolio_positions, rag_semantic_market_search and
         calculate_portfolio_risk_metrics return as_of, source and
         is_delayed at the top level. Propagate them.
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
    ("market_research", market_research_tools),
    ("risk_strategy", risk_strategy_tools),
    ("compliance", compliance_tools),
    ("transaction", transaction_tools),
    ("budget", budget_tools),
)


def build_server() -> FastMCP:
    """Register every domain module against the shared FastMCP instance."""
    for domain, module in DOMAIN_MODULES:
        module.register(mcp)
        log.info("registered domain: %s (%s)", domain, module.__name__)
    log.info("moneyfast mcp ready, contract %s, MOCK DATA ONLY", CONTRACT_VERSION)
    return mcp


build_server()


if __name__ == "__main__":
    # SADECE SSE İLE ÇALIŞTIR (host ve port'u sildik)
    mcp.run(transport="sse")