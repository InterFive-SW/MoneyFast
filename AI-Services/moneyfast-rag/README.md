# MoneyFast RAG service

Retrieval over the curated market-research corpus. Owns `vector-db` and the
embedding model; nothing else in the system holds a vector-db credential.

## Why this is a separate container

`docs/VECTOR_DB_ARCHITECTURE.md` assigns the vector database to a RAG service
rather than to the backend or the MCP tool server. Two reasons still hold:

* **Credential boundary.** `RAG_DB_USER` is `NOSUPERUSER` and scoped to DML in
  the `rag` schema plus `EXECUTE` on `rag.match_chunks`. Handing that to the
  MCP tool server would put a database credential in the process that
  evaluates model-supplied arguments.
* **Dependency profile.** ONNX Runtime and the tokenizer stack do not belong
  in the image that serves the banking API.

## Embeddings: local, free, offline

`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
via [fastembed](https://github.com/qdrant/fastembed), 384 dimensions, executed
on ONNX Runtime. It is the only 384-dimension multilingual model fastembed
supports — `intfloat/multilingual-e5-small` is not in its catalogue at all. There is **no embedding provider API
key anywhere in this system** — Groq provides LLM inference and does not offer
embedding models, and every hosted alternative either costs money or expires a
free tier mid-project.

fastembed rather than `sentence-transformers` because it avoids pulling torch:
roughly 100MB of dependencies instead of ~1GB.

Input prefixes belong to the model, not the call site. E5 models are
asymmetric and want `query: ` / `passage: `; this MiniLM paraphrase model is
symmetric and a prefix would only add tokens it never trained on.
`embeddings.py` resolves the prefix from the model name via `_PREFIX_RULES`
and defaults to none — the safe direction, since a missing prefix forgoes an
improvement while a spurious one costs recall. Switching `EMBEDDING_MODEL` to
an E5 or BGE model turns the right prefix on automatically.

The weights are baked into the image at build time. The `rag` container is not
on `ai-egress`, so a runtime download would hang rather than fail fast.

### Changing the model

Any change to `EMBEDDING_MODEL` or `EMBEDDING_DIMENSION` requires all four of:
a schema change to `rag.chunks.embedding` and `rag.match_chunks`, a full
re-embed of the corpus, a rerun of retrieval evaluation, and a rebuild of the
optional HNSW index. The `CHECK (embedding_model = ...)` constraint exists so a
partial migration fails at write time instead of quietly mixing vector spaces.

## API

| method | path | purpose |
|---|---|---|
| `GET` | `/healthz` | liveness |
| `GET` | `/readyz` | model resident **and** vector-db reachable |
| `POST` | `/search` | MCP v2.1 retrieval contract |
| `POST` | `/ingest` | load one document; idempotent by content hash |

`POST /search` is consumed by `rag_semantic_market_search` in the MCP tool
server. Its response satisfies `market_research_tools._normalize` field for
field, so that frozen function defaults nothing.

### Two documented deviations from the tool contract

* **`top_k` is clamped to 20.** The contract permits 25; `rag.match_chunks`
  rejects anything higher. Clamping here keeps a legal tool call from
  surfacing to the user as "research sources could not be consulted".
* **`rerank` is accepted and ignored.** A cross-encoder reranker would roughly
  triple the image size for a corpus this small. Results are ordered by cosine
  similarity. The flag stays in the signature because the contract is frozen.

### Failure semantics

An unreachable or erroring vector store returns **503**, which the MCP client
maps to `UpstreamUnavailableError`. It never returns an empty `200`: the
orchestrator reads `results: []` as "the corpus holds no evidence" and tells
the user so, which would be a false statement about a database that simply
went down.

An unrecognised filter key returns **400** rather than being dropped. Silently
ignoring `filters.tickers` turns a false negative into an apparent fact.

## Coreference resolution

The contract promises server-side resolution and a `query_echo`. This service
has no LLM and no egress — depending on Groq to ground Groq would be circular —
so the resolution is deliberately modest: a query shorter than four tokens is
prefixed with the most recent **user** turn from `conversation_context`. The
string actually embedded is always returned in `query_echo`, so a wrong
resolution is visible rather than mysterious.

## Local development

```bash
make install install-test
make test          # 95% coverage gate, no database or model required
```

The suite stubs both the embedder and the connection pool. Loading real ONNX
weights in CI would add ~90MB and several seconds to prove something the
model's authors already test.
