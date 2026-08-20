-- Index-compatible replacement for rag.match_chunks.
--
-- Signature, parameter names and RETURNS TABLE must stay byte-identical to
-- base/0003: CREATE OR REPLACE rejects a changed return type or a renamed
-- input parameter, so any drift here fails at apply time rather than at
-- query time.
CREATE OR REPLACE FUNCTION rag.match_chunks(
    p_query_embedding VECTOR(384),
    p_top_k INTEGER DEFAULT 5,
    p_match_threshold DOUBLE PRECISION DEFAULT NULL,
    p_tickers TEXT[] DEFAULT NULL,
    p_categories TEXT[] DEFAULT NULL,
    p_languages TEXT[] DEFAULT NULL,
    p_document_types TEXT[] DEFAULT NULL,
    p_published_after TIMESTAMPTZ DEFAULT NULL,
    p_published_before TIMESTAMPTZ DEFAULT NULL,
    p_publishers TEXT[] DEFAULT NULL
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
    language TEXT,
    category TEXT,
    metadata JSONB,
    similarity DOUBLE PRECISION
)
LANGUAGE plpgsql
STABLE
-- `public` is on the path because that is where CREATE EXTENSION vector
-- installs the `<=>` operator. Leaving it off compiles fine and fails only at
-- query time with "operator does not exist: public.vector <=> public.vector",
-- because PL/pgSQL resolves operators when the statement first executes, not
-- when the function is created.
--
-- Including it is safe here specifically because the application role holds no
-- CREATE on `public` and no direct grant on it, so nothing untrusted can be
-- planted there to shadow a name. vector-db-permissions-test.sql asserts both,
-- which is what keeps this line safe rather than merely convenient.
SET search_path = pg_catalog, rag, public
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
            d.ticker::TEXT AS ticker,
            d.document_type,
            d.language::TEXT AS language,
            d.category,
            c.metadata,
            (c.embedding <=> p_query_embedding)::DOUBLE PRECISION
                AS distance
        FROM rag.chunks AS c
        JOIN rag.documents AS d ON d.id = c.document_id
        WHERE d.status = 'active'
          AND (
              p_tickers IS NULL
              OR cardinality(p_tickers) = 0
              OR d.ticker = ANY(p_tickers)
          )
          AND (
              p_categories IS NULL
              OR cardinality(p_categories) = 0
              OR d.category = ANY(p_categories)
          )
          AND (
              p_languages IS NULL
              OR cardinality(p_languages) = 0
              OR d.language = ANY(p_languages)
          )
          AND (
              p_document_types IS NULL
              OR cardinality(p_document_types) = 0
              OR d.document_type = ANY(p_document_types)
          )
          AND (
              p_publishers IS NULL
              OR cardinality(p_publishers) = 0
              OR d.source = ANY(p_publishers)
          )
          AND (
              p_published_after IS NULL
              OR d.published_at >= p_published_after
          )
          AND (
              p_published_before IS NULL
              OR d.published_at <= p_published_before
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
        c.language,
        c.category,
        c.metadata,
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
    TEXT[],
    TEXT[],
    TEXT[],
    TEXT[],
    TIMESTAMPTZ,
    TIMESTAMPTZ,
    TEXT[]
) IS
    'Optional HNSW cosine retrieval with strict-order iterative scans for filtered active documents.';
