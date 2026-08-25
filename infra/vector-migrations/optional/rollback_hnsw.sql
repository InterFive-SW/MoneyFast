\set ON_ERROR_STOP on

BEGIN;

DROP INDEX IF EXISTS rag.idx_rag_chunks_embedding_hnsw;
\ir ../base/0003_create_exact_retrieval.sql

COMMIT;

\echo 'HNSW was disabled and exact retrieval was restored.'
\echo 'The base schema files are unchanged; re-enabling means re-applying'
\echo 'vector-migrations/optional/0001 and 0002 against this database.'
