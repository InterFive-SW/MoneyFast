# Vector DB architecture

## Runtime boundaries

MoneyFast uses two independent PostgreSQL 16 instances:

- `base-db` (`moneyfast`, `postgres_data`) stores application schemas:
  `auth`, `banking`, `investment`, `notification`, `analytics`, and the
  conversation-only `ai` schema.
- `vector-db` (`moneyfast_rag`, `vector_db_data`) uses pgvector and stores only
  `rag.documents` and `rag.chunks`.

Backend receives only the `base-db` connection string. The `rag` service
receives only a connection string built with `RAG_DB_USER` for `vector-db`.
The orchestrator (`agents`) and the MCP tool server (`mcp`) receive no
database credentials at all; `mcp` reaches retrieval over HTTP at
`RAG_API_BASE_URL`.

Database containers are isolated on separate Docker networks:

- `web-ingress`: `backend` only. The one non-internal network; Docker cannot
  publish a host port into an internal-only network, so the ingress service
  needs it
- `base-db-net`: `base-db` and `backend`
- `vector-db-net`: `vector-db` and `rag`
- `moneyfast-net`: internal application HTTP/MCP traffic (`backend`, `rag`,
  `mcp`, `agents`)

`agents` also joins `ai-egress` because the configured LLM provider (Groq) is
external. It is the only service with outbound access. `rag` deliberately does
not join it: the embedding model runs locally and needs no network, so a
misconfiguration cannot silently start calling a hosted provider. Database
containers never join that network. No database publishes a host port. FRP
must terminate only at the backend/frontend ingress.

The core volume key intentionally remains `postgres_data`, matching the
pre-isolation Compose file. Existing development data therefore stays attached
across the `postgres` -> `core-db` -> `base-db` service renames; no automatic copy,
rename, or deletion is performed. The vector database exclusively uses the
`vector_db_data` volume boundary. Compose still prefixes these keys with its project
name (normally `infra_` when run from this directory), so deployments must keep
the same project name they used before isolation.

PostgreSQL ignores `POSTGRES_USER` and `POSTGRES_PASSWORD` after a volume has
already been initialized. `BASE_DB_USER` therefore retains the previous
`moneyfast` role name. Existing-volume deployments must supply that volume's
actual existing password in both decoded and URL-encoded forms; changing the
environment does not rotate the database role.

`origin/main` already defined the `vector_db_data` key with administrator role
`moneyfast_ai`; this role name is retained for upgrade compatibility. If that
volume already exists, `VECTOR_DB_ADMIN_PASSWORD` must likewise match its
initialized credential. The PR never recreates or removes either volume.

## Ownership and startup

Core and vector schemas have separate owners:

1. `base-db` becomes healthy.
2. Backend runs only its core Alembic chain, then starts.
3. `vector-db` initialises itself. The files under
   `infra/vector-migrations/base/` are mounted into
   `/docker-entrypoint-initdb.d/` with numeric prefixes, and PostgreSQL's own
   entrypoint applies them in lexical order on first boot, followed by
   `40-grants.sh`.
4. `rag` waits for `vector-db` to be healthy, then exposes `/readyz` once the
   embedding model is loaded and the database answers.
5. `mcp` waits for `rag` to be healthy before it accepts tool calls.

The backend entrypoint must never touch the vector schema.

### Why there is no migration container

The previous design ran a one-shot `vector-migrations` job with a checksum
ledger (`rag_migrations.schema_migrations`) and two shell scripts. That is the
right machinery for a schema that evolves in production against data you
cannot lose. This corpus is dummy, re-ingestable, and rebuilt whenever the
embedding model changes — so the ledger was guarding nothing, at the cost of a
sixth container, a bespoke runner, and a startup ordering problem.

The trade-off is real and worth stating plainly: **`/docker-entrypoint-initdb.d/`
runs only when the data directory is empty.** Applying a future schema change
to an existing volume therefore means either dropping `vector_db_data` and
re-ingesting, or applying the SQL by hand:

```bash
docker compose exec -T vector-db \
  sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < vector-migrations/base/0004_whatever.sql
```

If the corpus ever becomes expensive to rebuild, reinstating a migration runner
is the correct response — but it belongs in `rag`'s startup path, not in a
container of its own.

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

- `BASE_DB_USER` is used only by the core database/backend path.
- `VECTOR_DB_ADMIN_USER` is a deployment/migration credential.
- `RAG_DB_USER` defaults to `rag_user` and is granted DML plus retrieval
  function access only in `moneyfast_rag.rag`.

Connection ownership:

```text
backend: postgresql://<base-user>:<secret>@base-db:5432/moneyfast
rag:     postgresql://<rag-user>:<secret>@vector-db:5432/moneyfast_rag
```

The backend currently accepts only `DATABASE_URL`. Compose therefore consumes
the complete `BASE_DATABASE_URL` instead of concatenating raw credentials.
Passwords containing `@`, `:`, `/`, `%`, or `#` must be percent-encoded in that
URL. `BASE_DB_PASSWORD` remains the decoded value supplied to PostgreSQL; both
values must describe the same credential. Neither value may be printed during
configuration validation.

The `rag` service must not receive the vector admin password. The backend must
not receive either vector credential. SQL files contain no passwords;
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

The model is `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`,
executed locally by the `rag` service through
[fastembed](https://github.com/qdrant/fastembed) on ONNX Runtime, with a
verified output dimension of 384. Therefore
`rag.chunks.embedding` is `VECTOR(384)`, and `embedding_model` is constrained
to that exact model name.

**There is no embedding provider API key anywhere in this system.** Groq
supplies LLM inference and offers no embedding models, and every hosted
alternative either costs money or expires a free tier mid-project. Running the
model locally also removes a network dependency from the retrieval path: `rag`
does not join `ai-egress`, and the ONNX weights are baked into its image at
build time, so a cold start cannot stall on a model download.

fastembed rather than `sentence-transformers` because it avoids pulling torch:
roughly 100MB of dependencies instead of about a gigabyte.

Configuration is `EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
and `EMBEDDING_DIMENSION=384` on the `rag` service.

This is the only 384-dimension multilingual model fastembed ships. Its
smallest E5 is `intfloat/multilingual-e5-large` at 1024 dimensions and 2.24GB,
which would mean both a schema change and a ten-fold larger image for no
retrieval gain at this corpus size.

Input prefixes are a property of the model family, not of the call site.
E5 models are asymmetric and want `query: ` / `passage: `; the MiniLM
paraphrase family is symmetric and is actively degraded by a prefix it never
saw in training. `rag/embeddings.py` resolves the prefix from the configured
model name and defaults to none, which is the safe direction: a missing prefix
forgoes an improvement, a spurious one costs recall.

Changing the model or output dimension requires:

1. a schema change to `rag.chunks.embedding` and `rag.match_chunks`,
2. rebuilding all embeddings,
3. rerunning retrieval evaluation,
4. rebuilding the optional vector index.

The `CHECK (embedding_model = ...)` constraint exists so that a partial
migration fails at write time rather than quietly mixing two vector spaces in
one index.

The Groq LLM configuration is unrelated to this embedding contract.

## Exact retrieval

`rag.match_chunks` performs exact cosine search and returns provenance with
each chunk. It:

- searches only `documents.status = 'active'`,
- supports `tickers`, `categories`, `languages`, `document_types`,
  `publishers`, `published_after`, and `published_before`,
- takes the list-valued filters as `TEXT[]` rather than scalars, because the
  MCP contract sends them as lists; narrowing to the first element would
  drop a filter the caller believes is applied, turning a false negative into
  an apparent fact. NULL and the empty array both mean "no filter",
- rejects `top_k` outside 1 through 20,
- defaults `top_k` to 5,
- accepts an optional caller-provided threshold,
- does not encode `0.75` or any other threshold as product truth,
- orders by cosine similarity descending,
- uses a fixed safe `search_path`, no dynamic SQL, and `STABLE` volatility.

The threshold must be selected from retrieval evaluation results. Similarity
measures semantic proximity, not truth, recency, or investment quality.

**Measured for the current model.** Cosine thresholds belong to the embedding
model, not to the product. The MCP contract documents a default of `0.62`,
which is calibrated for E5-family models; `paraphrase-multilingual-MiniLM`
scores lower. Against the live news corpus, a clearly relevant article scores
0.43-0.72 and off-topic ones sit below 0.35. At 0.62 the assistant reported
"no sources found" for news it was holding.

The orchestrator therefore sends `RAG_MIN_SIMILARITY`, default **0.35**. Re-measure
it whenever the embedding model changes — the number is not portable between
models, and neither is the contract's default.
`rag.documents.updated_at` is maintained by a database trigger on every
update; callers do not need to manufacture timestamps.

## Optional HNSW migration

Files under `infra/vector-migrations/optional/` are intentionally excluded from
the `/docker-entrypoint-initdb.d/` mounts, so they never run automatically.
Apply them only after corpus-size and latency benchmarks show that exact
search is insufficient:

```bash
cd infra
for file in vector-migrations/optional/000*.sql; do
  docker compose exec -T vector-db \
    sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$file"
done
```

The optional migration requires pgvector 0.8 or newer, creates a
`vector_cosine_ops` HNSW index with default parameters, enables strict-order
iterative scans for metadata filters, and replaces the retrieval function with
an index-compatible `ORDER BY embedding <=> query LIMIT top_k` query. Threshold
filtering remains in the outer query. Parameter tuning requires measured
recall/latency results and `EXPLAIN` must demonstrate index use.

`optional/rollback_hnsw.sql` drops the index and restores exact retrieval by
re-applying `base/0003`. The optional files are idempotent
(`CREATE OR REPLACE`), so re-enabling means simply running them again. Their
signature and `RETURNS TABLE` must stay byte-identical to `base/0003`:
`CREATE OR REPLACE FUNCTION` rejects a changed return type or a renamed input
parameter, so drift fails at apply time rather than at query time.

## Resource isolation

Two PostgreSQL containers isolate query execution, failure/restart domains,
volumes, and configurable CPU/memory ceilings. They do not automatically
reduce aggregate RAM; the sum of both limits and non-PostgreSQL services must
fit the Docker host.

Compose uses `mem_limit` and `cpus` independently for each DB. Values in
`infra/.env.example` are local-development examples, not production sizing.
Production values require load tests for core traffic and retrieval traffic.

`rag` service limits:

- default `top_k`: 5
- maximum `top_k`: 20. The MCP contract permits 25; `rag` clamps to 20 rather
  than letting `rag.match_chunks` raise, because the exception would reach the
  user as "research sources could not be consulted" for a legal tool call
- request timeout: configuration, not a source constant
- chunk/context token budget: decide from the selected LLM context window
- concurrency limit: decide from measured DB and local-embedding throughput
- maximum retrieval rounds: one by default; increases require evaluation

## Non-destructive runtime validation

Use an isolated project name and never add `down -v`:

```bash
cd infra
COMPOSE_PROJECT_NAME=moneyfast_vector_test \
  docker compose --env-file .env up -d vector-db
# Initialisation already ran; confirm the schema landed.
COMPOSE_PROJECT_NAME=moneyfast_vector_test \
  docker compose --env-file .env exec -T vector-db \
  sh -c 'psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\d rag.chunks"'

COMPOSE_PROJECT_NAME=moneyfast_vector_test \
  docker compose --env-file .env exec -T vector-db \
  sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < vector-db-smoke-test.sql
```

The smoke test rolls its own transaction back, so it can be run repeatedly
against the same volume.

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

It **includes market news**, ingested from Turkish financial RSS feeds by the
`ingestor` service and tagged `document_type = 'NEWS'` with its real
`published_at`.

This reverses the original exclusion, and the reason is that the exclusion
contradicted a frozen contract: `rag_semantic_market_search` lists `NEWS` as a
valid `doc_type` and describes the corpus as including news wires. When two
documents disagree, the one the code is written against wins.

It still excludes live prices, balances, portfolios, orders, trades, and
personal data. Those live in `base-db` and are reached through the backend.

- `vector-db` (via `rag`): sourced unstructured documents
- `backend` market module: current prices and market data
- `backend` investment module: user positions, orders, and trades
