# Social Signals — Operational Runbook

End-to-end path validated in Phase 4 (synthetic data only):

```text
Allowlisted X account (ingestor, optional)
        ↓  POST /api/market/social/ingest  (Bearer BACKEND_API_KEY)
Core PostgreSQL  market.social_*  (migration 0012)
        ↓  GET /api/market/social-signals
MCP  get_social_market_signals  (HTTP only — no DB, no X token)
        ↓
Market Research Agent  (flag MARKET_RESEARCH_SOCIAL_SIGNALS_ENABLED)
        ↓  ChatResponse.citations
Backend chat + Message.meta JSONB
        ↓
Frontend CitationList  (KAP primary / X secondary; URL allowlist)
```

## Credential ownership

| Secret | Owner | Notes |
|---|---|---|
| `X_BEARER_TOKEN` / `X_BEARER_TOKEN_FILE` | **ingestor only** | Prefer Docker secret file. Never give to backend, MCP, or agents. |
| `BACKEND_API_KEY` | backend + callers that ingest (ingestor) | Guards `POST /api/market/social/ingest`. Unset → ingest returns 503. |
| Core `DATABASE_URL` | **backend only** | MCP and agents must not hold it. |
| Groq key | **agents only** | Not required for ingest/read/MCP selection tests. |

See `infra/.env.example` and `infra/docker-compose.secrets.example.yml`.

## Defaults (safe)

- `X_INGEST_ENABLED=false` — no live X polling.
- `MARKET_RESEARCH_SOCIAL_SIGNALS_ENABLED=false` — Market Research does not call social MCP.
- Social feature stays **off** until explicitly enabled per environment.

## Enabling social signals safely

1. Set `BACKEND_API_KEY` (strong random) on backend and ingestor.
2. Keep `X_INGEST_ENABLED=false` until allowlist and rate limits are reviewed.
3. Configure allowlist JSON, for example:

```json
[{"handle":"mf_kap_synth","source_type":"disclosure_aggregator","trust_score":0.9,"is_active":true}]
```

   The string `kap_bildirimleri` is only a **configuration example** of a disclosure-aggregator style account. It is **not** a verified or recommended source. X handles must match `^[a-z0-9_]{1,15}$` (max 15 characters).

4. Prefer `X_BEARER_TOKEN_FILE` via the secrets overlay when enabling live X.
5. Enable `MARKET_RESEARCH_SOCIAL_SIGNALS_ENABLED=true` on **agents** only after ingest + public GET + MCP are healthy.
6. Roll out: migrate (0012) → ingest path → public GET → MCP → flag on agents → chat UI.

## Synthetic local validation (no real X / Groq)

Use an isolated Compose project name (never reuse `infra` volumes):

```bash
COMPOSE_PROJECT_NAME=moneyfast_social_e2e_p4 \
  docker compose -f /path/to/tmp/compose.p4.yml up -d --build base-db backend
# Host port example: 18000 — must not collide with the normal stack on 8000.
```

Then:

1. `POST /api/market/social/ingest` with `Authorization: Bearer <synthetic key>` and synthetic accounts/posts.
2. Replay the same batch — expect duplicate counters, no double rows.
3. `GET /api/market/social-signals?symbol=ASELS&since_hours=168` — camelCase, no `rawMetadata`, tombstones excluded.
4. Package tests (no live LLM): MCP server suite; orchestrator `tests/test_social_research.py` with `fake_llm` / `fake_mcp`.
5. Frontend: `npm test`, `npm run typecheck`, `npm run build` (citation contract).

Tear down **only** that project:

```bash
COMPOSE_PROJECT_NAME=moneyfast_social_e2e_p4 docker compose -f …/compose.p4.yml down --volumes
```

Never `docker system prune` or unscoped `down -v` against the normal MoneyFast stack.

## Production rollout / rollback

**Rollout:** confirm Alembic head includes `0012` → set `BACKEND_API_KEY` → allowlist → optional X ingest → enable Market Research flag → monitor MCP timeouts and KAP accept/reject counters.

**Rollback / disable:** set `MARKET_RESEARCH_SOCIAL_SIGNALS_ENABLED=false` and/or `X_INGEST_ENABLED=false`. Chat continues without social citations. Data in `market.social_*` can remain; no migration downgrade required for disable.

## Rate limits, cursors, health

- Ingestor: `X_POLL_INTERVAL_MINUTES` (min 5), `X_MAX_PAGES_PER_ACCOUNT`, `X_BACKEND_BATCH_SIZE`.
- Cursor/checkpoint file: `X_STATE_FILE` (default `/app/state/x-cursors.json` on volume `ingestor_x_state`).
- MCP: backend HTTP timeouts/retries only — fail soft if backend 5xx.
- Backend: no dedicated social health route; public `GET /api/market/social-signals` returning `[]` or data is the smoke signal. MCP exposes TCP health on its port.

## Caveats

- Social evidence is research support, **not** financial advice. “Verified” / KAP linkage does not guarantee correctness.
- KAP URLs are discovery links re-validated on allowlisted hosts; the product does not scrape KAP.
- Frontend re-validates citation URLs (HTTPS X status + `kap.org.tr` only) before rendering links.

## Related code

- Migration: `backend/alembic/versions/0012_social_signals.py`
- Ingest / public API: `backend/app/modules/market/router.py`
- MCP tool: `get_social_market_signals` in `mcp-server/social_signals_tools.py`
- Flag: `MARKET_RESEARCH_SOCIAL_SIGNALS_ENABLED` (`social_research.FLAG`)
- UI: `frontend/src/components/chat/CitationList.tsx`, `frontend/src/lib/researchCitations.ts`
