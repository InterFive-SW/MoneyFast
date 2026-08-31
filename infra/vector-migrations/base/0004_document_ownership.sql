-- Document ownership.
--
-- Until now every document in rag.documents was reachable by every query.
-- That was correct while the corpus held only news: one shared, public body
-- of financial text. Users can now upload their own files, and a private
-- document that any other user's query can retrieve is not a feature with a
-- bug in it -- it is a disclosure.
--
-- NULL owner means the public corpus (news). A non-NULL owner means exactly
-- one person may retrieve it.

ALTER TABLE rag.documents
    ADD COLUMN owner_user_id UUID;

COMMENT ON COLUMN rag.documents.owner_user_id IS
    'NULL = public corpus (news). Non-NULL = private to that user.';

-- Deduplication becomes per-owner.
--
-- The old constraint was UNIQUE (content_hash) across the whole table, so the
-- SECOND person to upload a given file got "duplicate" and no document of
-- their own -- their copy silently belonged to whoever uploaded it first.
--
-- Two PARTIAL indexes rather than one UNIQUE (owner_user_id, content_hash):
-- in a composite unique index NULLs compare as distinct, so the public corpus
-- would lose its deduplication entirely and every ingestor cycle would write
-- the same articles again.
ALTER TABLE rag.documents
    DROP CONSTRAINT documents_content_hash_key;

CREATE UNIQUE INDEX uq_rag_documents_public_hash
    ON rag.documents (content_hash)
    WHERE owner_user_id IS NULL;

CREATE UNIQUE INDEX uq_rag_documents_owner_hash
    ON rag.documents (owner_user_id, content_hash)
    WHERE owner_user_id IS NOT NULL;

CREATE INDEX idx_rag_documents_owner
    ON rag.documents (owner_user_id)
    WHERE owner_user_id IS NOT NULL;

-- The old function must GO, not be replaced.
--
-- CREATE OR REPLACE with a different parameter list creates an OVERLOAD: the
-- ten-argument version would still exist and still return every user's
-- documents to any caller that omitted the owner. Dropping it means such a
-- call fails to resolve instead.
DROP FUNCTION IF EXISTS rag.match_chunks(
    VECTOR, INTEGER, DOUBLE PRECISION, TEXT[], TEXT[], TEXT[], TEXT[],
    TIMESTAMPTZ, TIMESTAMPTZ, TEXT[]
);

-- p_owner_user_id has NO DEFAULT, and sits second so that it cannot be.
--
-- A default would mean a call site that was never updated keeps working and
-- quietly reads everyone's files. Without one, PostgreSQL cannot resolve the
-- call at all: the failure is loud, immediate, and impossible to ship past.
CREATE FUNCTION rag.match_chunks(
    p_query_embedding VECTOR(384),
    p_owner_user_id UUID,
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
-- See 0003 for why `public` is on the path and why that is safe here.
SET search_path = pg_catalog, rag, public
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
            d.ticker::TEXT AS ticker,
            d.document_type,
            d.language::TEXT AS language,
            d.category,
            c.metadata,
            (1 - (c.embedding <=> p_query_embedding))::DOUBLE PRECISION
                AS similarity
        FROM rag.chunks AS c
        JOIN rag.documents AS d ON d.id = c.document_id
        WHERE d.status = 'active'
          -- The ownership gate. An anonymous caller passes NULL and the
          -- second arm is never true, so they see the public corpus only:
          -- `owner_user_id = NULL` is NULL, not true, for every row.
          AND (
              d.owner_user_id IS NULL
              OR d.owner_user_id = p_owner_user_id
          )
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
        s.language,
        s.category,
        s.metadata,
        s.similarity
    FROM scored AS s
    WHERE p_match_threshold IS NULL
       OR s.similarity >= p_match_threshold
    ORDER BY s.similarity DESC, s.chunk_id
    LIMIT p_top_k;
END;
$$;

COMMENT ON FUNCTION rag.match_chunks(
    VECTOR, UUID, INTEGER, DOUBLE PRECISION, TEXT[], TEXT[], TEXT[], TEXT[],
    TIMESTAMPTZ, TIMESTAMPTZ, TEXT[]
) IS
    'Exact cosine retrieval over the public corpus plus the caller''s own documents. The owner argument has no default: omitting it must fail, not widen the result.';
