CREATE OR REPLACE FUNCTION rag.match_chunks(
    p_query_embedding VECTOR(1536),
    p_top_k INTEGER DEFAULT 5,
    p_match_threshold DOUBLE PRECISION DEFAULT NULL,
    p_ticker TEXT DEFAULT NULL,
    p_category TEXT DEFAULT NULL,
    p_language TEXT DEFAULT NULL,
    p_document_type TEXT DEFAULT NULL,
    p_published_after TIMESTAMPTZ DEFAULT NULL
)
RETURNS TABLE (
    chunk_id UUID,
    document_id UUID,
    content TEXT,
    title TEXT,
    source TEXT,
    source_url TEXT,
    published_at TIMESTAMPTZ,
    ticker TEXT,
    document_type TEXT,
    similarity DOUBLE PRECISION
)
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, rag
SET hnsw.iterative_scan = 'strict_order'
AS $$
BEGIN
    IF p_query_embedding IS NULL THEN
        RAISE EXCEPTION 'query_embedding is required'
            USING ERRCODE = '22004';
    END IF;

    IF p_top_k < 1 OR p_top_k > 20 THEN
        RAISE EXCEPTION 'top_k must be between 1 and 20'
            USING ERRCODE = '22023';
    END IF;

    IF p_match_threshold IS NOT NULL
       AND (p_match_threshold < -1 OR p_match_threshold > 1) THEN
        RAISE EXCEPTION 'match_threshold must be between -1 and 1'
            USING ERRCODE = '22023';
    END IF;

    RETURN QUERY
    WITH candidates AS MATERIALIZED (
        SELECT
            c.id AS chunk_id,
            c.document_id,
            c.content,
            d.title,
            d.source,
            d.source_url,
            d.published_at,
            d.ticker,
            d.document_type,
            (c.embedding <=> p_query_embedding)::DOUBLE PRECISION
                AS distance
        FROM rag.chunks AS c
        JOIN rag.documents AS d ON d.id = c.document_id
        WHERE d.status = 'active'
          AND (p_ticker IS NULL OR d.ticker = p_ticker)
          AND (p_category IS NULL OR d.category = p_category)
          AND (p_language IS NULL OR d.language = p_language)
          AND (
              p_document_type IS NULL
              OR d.document_type = p_document_type
          )
          AND (
              p_published_after IS NULL
              OR d.published_at >= p_published_after
          )
        ORDER BY c.embedding <=> p_query_embedding
        LIMIT p_top_k
    )
    SELECT
        c.chunk_id,
        c.document_id,
        c.content,
        c.title,
        c.source,
        c.source_url,
        c.published_at,
        c.ticker,
        c.document_type,
        (1 - c.distance)::DOUBLE PRECISION AS similarity
    FROM candidates AS c
    WHERE p_match_threshold IS NULL
       OR (1 - c.distance) >= p_match_threshold
    ORDER BY c.distance, c.chunk_id;
END;
$$;

COMMENT ON FUNCTION rag.match_chunks(
    VECTOR,
    INTEGER,
    DOUBLE PRECISION,
    TEXT,
    TEXT,
    TEXT,
    TEXT,
    TIMESTAMPTZ
) IS
    'Optional HNSW cosine retrieval with strict-order iterative scans for filtered active documents.';
