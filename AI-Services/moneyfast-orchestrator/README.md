# MoneyFast Orchestrator

LangGraph orchestrator for the MoneyFast multi-agent financial assistant.
Talks to the `mcp` MCP server over SSE across a Docker network.

## Layout

| File | Role |
|------|------|
| `orchestrator.py` | State schema, nodes, conditional edges, graph, CLI |
| `prompts.py` | Turkish user-facing prompt + 5 backend specialist prompts |
| `mcp_client.py` | MCP SSE client, retry, fail-closed error types |
| `api.py` | FastAPI: `/chat`, `/healthz`, `/readyz` |
| `social_research.py` | Feature flag + config for optional X social evidence on market research |

## Graph

```
START -> router -> {portfolio | market_research | risk | transaction |
                    handoff | synthesis} -> synthesis -> compliance
compliance --BLOCK (budget left)--> synthesis
compliance --PASS | REVISE | budget exhausted--> END
```

`router` and `compliance` are deterministic tool calls, not LLM judgement
calls. Compliance fails closed: an unreachable rule engine yields BLOCK, never
a bypass.

## Run

The whole stack is defined in `infra/docker-compose.yml`; this directory no
longer carries its own Compose file, because the orchestrator cannot run
usefully without `mcp`, `backend` and `rag` alongside it.

```bash
cp .env.example .env      # add GROQ_API_KEY
cd ../../infra && docker compose --env-file .env up -d --build
# The orchestrator is not published to the host. Reach it through the backend:
curl -s localhost:8000/api/ai_orchestrator/health | jq
curl -s localhost:8000/api/ai_orchestrator/chat -H 'content-type: application/json' \
  -d '{"user_message":"portföyüm ne durumda?","user_id":"TEST-USER-1"}' | jq -r .final_output
```

Locally without Docker:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export MCP_SERVER_URL=http://localhost:8000/sse
python orchestrator.py "nereden başlamalıyım?"
```

## Notes

- `MCP_SERVER_URL` uses the container name inside compose. `localhost` inside a
  container is that container.
- `risk` makes two tool calls: the risk tool has no position access by design,
  so the graph fetches holdings first.
- Specialist planning uses `GROQ_FAST_MODEL` (8b) since it only emits argument
  JSON. Turkish synthesis uses the 70b model, where quality actually shows.
- Only `final_output` crosses to the client. `specialist_output` and
  `draft_response` stay server side.
- Groq enforces per-minute token limits. A portfolio turn costs roughly three
  LLM calls; add a 429 backoff before you put real traffic on this.
- Market research can optionally attach Phase 1 social signals after RAG via
  MCP tool `get_social_market_signals`. Disabled by default
  (`MARKET_RESEARCH_SOCIAL_SIGNALS_ENABLED=false`). Social posts are supporting
  evidence only; answers may include structured `citations` (never raw metadata).
