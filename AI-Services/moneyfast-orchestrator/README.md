# MoneyFast Orchestrator

LangGraph orchestrator for the MoneyFast multi-agent financial assistant.
Talks to the `mcp-market-data` MCP server over SSE across a Docker network.

## Layout

| File | Role |
|------|------|
| `orchestrator.py` | State schema, nodes, conditional edges, graph, CLI |
| `prompts.py` | Turkish user-facing prompt + 5 backend specialist prompts |
| `mcp_client.py` | MCP SSE client, retry, fail-closed error types |
| `api.py` | FastAPI: `/chat`, `/healthz`, `/readyz` |

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

```bash
cp .env.example .env      # add GROQ_API_KEY
docker compose up --build
curl -s localhost:8080/readyz | jq
curl -s localhost:8080/chat -H 'content-type: application/json' \
  -d '{"user_message":"portföyüm ne durumda?","user_id":"u_1"}' | jq -r .final_output
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
