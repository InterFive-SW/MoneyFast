\set ON_ERROR_STOP on

BEGIN;

INSERT INTO rag.documents (
    id,
    title,
    source,
    category,
    language,
    ticker,
    document_type,
    content_hash,
    status
)
SELECT
    ('10000000-0000-0000-0000-' || lpad(g::TEXT, 12, '0'))::UUID,
    'HNSW test document ' || g,
    'TEST',
    'company-report',
    'tr',
    CASE WHEN g % 2 = 0 THEN 'THYAO' ELSE 'ASELS' END,
    'annual-report',
    md5(g::TEXT) || md5('hnsw-' || g::TEXT),
    'active'
FROM generate_series(1, 1000) AS g;

INSERT INTO rag.chunks (
    document_id,
    chunk_index,
    content,
    embedding,
    embedding_model,
    token_count
)
SELECT
    d.id,
    0,
    'HNSW test chunk for ' || d.ticker,
    (
        ARRAY[1::real, (substring(d.id::TEXT, 34, 3)::INTEGER / 1000.0)::real]
        || array_fill(0::real, ARRAY[1534])
    )::vector,
    'text-embedding-3-small',
    5
FROM rag.documents AS d
WHERE d.id::TEXT LIKE '10000000-0000-0000-0000-%';

ANALYZE rag.documents;
ANALYZE rag.chunks;

SET LOCAL enable_seqscan = off;

DO $$
DECLARE
    query_vector VECTOR(1536) :=
        (ARRAY[1::real] || array_fill(0::real, ARRAY[1535]))::vector;
    plan JSON;
    result_count INTEGER;
BEGIN
    EXECUTE format(
        $query$
        EXPLAIN (FORMAT JSON)
        SELECT c.id
        FROM rag.chunks AS c
        JOIN rag.documents AS d ON d.id = c.document_id
        WHERE d.status = 'active'
          AND d.ticker = 'THYAO'
        ORDER BY c.embedding <=> %L::vector
        LIMIT 5
        $query$,
        query_vector::TEXT
    )
    INTO plan;

    IF plan::TEXT NOT LIKE '%idx_rag_chunks_embedding_hnsw%' THEN
        RAISE EXCEPTION 'HNSW index was not used: %', plan;
    END IF;

    SELECT count(*)
    INTO result_count
    FROM rag.match_chunks(
        query_vector,
        5,
        NULL,
        'THYAO',
        'company-report',
        'tr',
        'annual-report',
        NULL
    );

    IF result_count <> 5 THEN
        RAISE EXCEPTION 'HNSW retrieval returned % rows instead of 5', result_count;
    END IF;
END;
$$;

ROLLBACK;
