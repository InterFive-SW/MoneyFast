\set ON_ERROR_STOP on

BEGIN;

DROP INDEX IF EXISTS rag.idx_rag_chunks_embedding_hnsw;
\ir ../base/0003_create_exact_retrieval.sql

COMMIT;

\echo 'HNSW was disabled. Applied migration history was preserved.'
\echo 'Re-enabling requires a new numbered optional migration.'
