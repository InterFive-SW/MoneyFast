DO $$
DECLARE
    version_parts TEXT[];
BEGIN
    SELECT string_to_array(extversion, '.')
    INTO version_parts
    FROM pg_catalog.pg_extension
    WHERE extname = 'vector';

    IF version_parts IS NULL
       OR version_parts[1]::INTEGER < 0
       OR (
           version_parts[1]::INTEGER = 0
           AND version_parts[2]::INTEGER < 8
       ) THEN
        RAISE EXCEPTION
            'pgvector 0.8.0 or newer is required for filtered HNSW iterative scans';
    END IF;
END;
$$;

CREATE INDEX idx_rag_chunks_embedding_hnsw
    ON rag.chunks
    USING hnsw (embedding vector_cosine_ops);
