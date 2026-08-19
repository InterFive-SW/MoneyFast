# Vector DB architecture

## Runtime boundaries

MoneyFast uses two independent PostgreSQL 16 instances:

- `core-db` (`moneyfast`, `postgres_data`) stores application schemas:
  `auth`, `banking`, `investment`, `notification`, `analytics`, and the
  conversation-only `ai` schema.
- `vector-db` (`moneyfast_rag`, `vector_db_data`) uses pgvector and stores only
  `rag.documents` and `rag.chunks`.

Backend receives only the `core-db` connection string. The future RAG service
must receive only a connection string built with `RAG_DB_USER` for
`vector-db`. The orchestrator and MCP Tools receive no database credentials.
The orchestrator will call the RAG service over HTTP. MCP transport migration
is owned by a separate PR and is not changed by this Vector DB work.

Database containers are isolated on separate Docker networks:

- `core-db-net`: `core-db` and backend
- `vector-db-net`: `vector-db`, vector migrations, and the future RAG service
- `moneyfast-net`: internal application HTTP/MCP traffic

The orchestrator also joins `ai-egress` because the configured LLM provider is
external. Database containers never join that network. No database publishes a
host port. FRP must terminate only at the backend/frontend ingress.

The core volume key intentionally remains `postgres_data`, matching the
pre-isolation Compose file. Existing development data therefore stays attached
when the service is renamed from `postgres` to `core-db`; no automatic copy,
rename, or deletion is performed. The vector database exclusively uses the
`vector_db_data` volume boundary. Compose still prefixes these keys with its project
name (normally `infra_` when run from this directory), so deployments must keep
the same project name they used before isolation.

PostgreSQL ignores `POSTGRES_USER` and `POSTGRES_PASSWORD` after a volume has
already been initialized. `CORE_DB_USER` therefore retains the previous
`moneyfast` role name. Existing-volume deployments must supply that volume's
actual existing password in both decoded and URL-encoded forms; changing the
environment does not rotate the database role.

`origin/main` already defined the `vector_db_data` key with administrator role
`moneyfast_ai`; this role name is retained for upgrade compatibility. If that
volume already exists, `VECTOR_DB_ADMIN_PASSWORD` must likewise match its
initialized credential. The PR never recreates or removes either volume.

## Ownership and startup

Core and vector migrations have separate owners:

1. `core-db` becomes healthy.
2. Backend runs only its core Alembic chain, then starts.
3. `vector-db` becomes healthy.
4. The one-shot `vector-migrations` job applies each immutable SQL file under
   `infra/vector-migrations/base/` exactly once, verifies checksums against
   `rag_migrations.schema_migrations`, and then refreshes application grants.
5. A future RAG service must depend on successful vector migrations and expose
   readiness before the orchestrator starts using retrieval.

The backend entrypoint must never run vector migrations. Until a RAG service
repository exists, `vector-migrations` is the explicit owner; no placeholder
RAG container is created.

`infra/intertech.sql` is the core schema reference. It deliberately contains
`ai.conversations` and `ai.messages`, but no vector extension, `ai.rag_*`
tables, `rag` schema, or cross-database references.

### Existing core migration blocker

The runtime source of truth on `origin/main` is currently backend Alembic:
`backend/docker-entrypoint.sh` runs `alembic upgrade head`, while Compose does
not mount or execute `infra/intertech.sql`. The tracked Alembic chain creates
`public.users`, matching the current auth ORM's table location. Its columns are
also stale: migration `0001` creates `full_name`, while the ORM requires
`tc_no`, `first_name`, `last_name`, and `phone_number`. The chain does not create the
`banking`, `investment`, `notification`, `analytics`, or `ai` schemas described
by `intertech.sql`.

This Vector DB PR preserves that behavior and the existing `postgres_data`
volume; it does not introduce a second users table or pretend the missing core
migrations exist. A separate coordinated core-migration task must choose and
migrate to one contract before clean-volume creation of every documented core
schema can be claimed.

## Credentials

Copy `infra/.env.example` to `infra/.env` and replace every `change-me` value.
Do not commit `infra/.env`.

- `CORE_DB_USER` is used only by the core database/backend path.
- `VECTOR_DB_ADMIN_USER` is a deployment/migration credential.
- `RAG_DB_USER` defaults to `rag_user` and is granted DML plus retrieval
  function access only in `moneyfast_rag.rag`.

Connection ownership:

```text
Backend:     postgresql://<core-user>:<secret>@core-db:5432/moneyfast
RAG Service: postgresql://<rag-user>:<secret>@vector-db:5432/moneyfast_rag
```

The backend currently accepts only `DATABASE_URL`. Compose therefore consumes
the complete `CORE_DATABASE_URL` instead of concatenating raw credentials.
Passwords containing `@`, `:`, `/`, `%`, or `#` must be percent-encoded in that
URL. `CORE_DB_PASSWORD` remains the decoded value supplied to PostgreSQL; both
values must describe the same credential. Neither value may be printed during
configuration validation.

The RAG application must not receive the vector admin password. The backend
must not receive either vector credential. SQL files contain no passwords;
role passwords are injected by the deployment job.

For local development, `RAG_DB_PASSWORD` is an explicit environment fallback.
It is read through psql's `\getenv`, never passed as a process argument.
Production should use `docker-compose.secrets.example.yml`, set
`RAG_DB_PASSWORD_SECRET_FILE`, and leave the environment fallback empty. The
bootstrap script reads the mounted file without printing its content.

The vector administrator owns migration objects and default privileges.
`rag_user` receives only schema usage, table DML, sequence usage, and execution
of `rag.match_chunks`. It receives no access to the private migration ledger
and is explicitly `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, and
`NOREPLICATION`. Grant management is limited to the current vector database
and its `rag` objects; it does not revoke or alter privileges on any other
database in the PostgreSQL cluster.

## Embedding contract

The selected provider is the OpenAI API and the model is
`text-embedding-3-small`, with a verified output dimension of 1536. Therefore
`rag.chunks.embedding` is
`VECTOR(1536)`, and `embedding_model` is constrained to that exact model name.
The future RAG service must receive `OPENAI_API_KEY` as a secret and
`EMBEDDING_MODEL=text-embedding-3-small`,
`EMBEDDING_DIMENSION=1536` as configuration; no API key belongs in SQL,
Compose, or documentation.

Changing the model or output dimension requires:

1. a new schema migration,
2. rebuilding all embeddings,
3. rerunning retrieval evaluation,
4. rebuilding the optional vector index.

The Groq LLM configuration is unrelated to this embedding contract.

## Exact retrieval

`rag.match_chunks` performs exact cosine search and returns provenance with
each chunk. It:

- searches only `documents.status = 'active'`,
- supports `ticker`, `category`, `language`, `document_type`, and
  `published_after`,
- rejects `top_k` outside 1 through 20,
- defaults `top_k` to 5,
- accepts an optional caller-provided threshold,
- does not encode `0.75` or any other threshold as product truth,
- orders by cosine similarity descending,
- uses a fixed safe `search_path`, no dynamic SQL, and `STABLE` volatility.

The threshold must be selected from retrieval evaluation results. Similarity
measures semantic proximity, not truth, recency, or investment quality.
`rag.documents.updated_at` is maintained by a database trigger on every
update; callers do not need to manufacture timestamps.

## Optional HNSW migration

Files under `infra/vector-migrations/optional/` are intentionally excluded from
the Compose migration job. Apply them only after corpus-size and latency
benchmarks show that exact search is insufficient:

```bash
docker compose --env-file .env run --rm --no-deps \
  --entrypoint /scripts/run-vector-migrations.sh \
  vector-migrations /migrations/optional
```

The optional migration requires pgvector 0.8 or newer, creates a
`vector_cosine_ops` HNSW index with default parameters, enables strict-order
iterative scans for metadata filters, and replaces the retrieval function with
an index-compatible `ORDER BY embedding <=> query LIMIT top_k` query. Threshold
filtering remains in the outer query. Parameter tuning requires measured
recall/latency results and `EXPLAIN` must demonstrate index use.

`optional/rollback_hnsw.sql` drops the index and restores exact retrieval while
preserving migration history. Re-enabling after rollback requires a new
numbered migration; applied migration files are never edited or replayed.

## Resource isolation

Two PostgreSQL containers isolate query execution, failure/restart domains,
volumes, and configurable CPU/memory ceilings. They do not automatically
reduce aggregate RAM; the sum of both limits and non-PostgreSQL services must
fit the Docker host.

Compose uses `mem_limit` and `cpus` independently for each DB. Values in
`infra/.env.example` are local-development examples, not production sizing.
Production values require load tests for core traffic and retrieval traffic.

Future RAG service limits:

- default `top_k`: 5
- maximum `top_k`: 20
- request timeout: configuration, not a source constant
- chunk/context token budget: decide from the selected LLM context window
- concurrency limit: decide from measured DB and embedding-provider capacity
- maximum retrieval rounds: one by default; increases require evaluation

## Non-destructive runtime validation

Use an isolated project name and never add `down -v`:

```bash
cd infra
COMPOSE_PROJECT_NAME=moneyfast_vector_test \
  docker compose --env-file .env up -d core-db vector-db
COMPOSE_PROJECT_NAME=moneyfast_vector_test \
  docker compose --env-file .env run --rm vector-migrations
# Run a second time to verify checksum-validated skips.
COMPOSE_PROJECT_NAME=moneyfast_vector_test \
  docker compose --env-file .env run --rm vector-migrations

COMPOSE_PROJECT_NAME=moneyfast_vector_test \
  docker compose --env-file .env exec -T vector-db \
  sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < vector-db-smoke-test.sql
```

Run `vector-db-permissions-test.sql` as the vector administrator with
`RAG_DB_USER` present in the process environment. After benchmark data is
loaded, apply the optional migrations, run
`vector-db-hnsw-smoke-test.sql`, and inspect its `EXPLAIN` assertion. Stop only
the isolated test project's containers; retain volumes unless deletion is
separately approved.

## Corpus boundary

The MVP vector corpus includes general financial education and sourced,
dated documents for THYAO, ASELS, TUPRS, EREGL, and BIMAS: company profiles,
activity reports, investor presentations, and selected KAP disclosures.

It excludes news feeds, live prices, balances, portfolios, orders, trades, and
personal data.

- Vector DB: sourced unstructured documents
- MCP Market Data: current prices and market data
- Investment DB Service: user positions, orders, and trades
