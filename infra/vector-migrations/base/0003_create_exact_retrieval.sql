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
    WITH scored AS MATERIALIZED (
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
            (1 - (c.embedding <=> p_query_embedding))::DOUBLE PRECISION
                AS similarity
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
    )
    SELECT
        s.chunk_id,
        s.document_id,
        s.content,
        s.title,
        s.source,
        s.source_url,
        s.published_at,
        s.ticker,
        s.document_type,
        s.similarity
    FROM scored AS s
    WHERE p_match_threshold IS NULL
       OR s.similarity >= p_match_threshold
    ORDER BY s.similarity DESC, s.chunk_id
    LIMIT p_top_k;
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
    'Exact cosine retrieval for active public financial documents. Threshold is caller-configured, not a product constant.';
