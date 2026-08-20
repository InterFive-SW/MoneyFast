CREATE TABLE rag.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL CHECK (btrim(title) <> ''),
    source TEXT NOT NULL CHECK (btrim(source) <> ''),
    source_url TEXT,
    category TEXT NOT NULL CHECK (btrim(category) <> ''),
    language VARCHAR(10) NOT NULL DEFAULT 'tr'
        CHECK (btrim(language) <> ''),
    ticker VARCHAR(20),
    document_type TEXT NOT NULL CHECK (btrim(document_type) <> ''),
    period TEXT,
    published_at TIMESTAMPTZ,
    content_hash VARCHAR(64) NOT NULL UNIQUE
        CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (
            status IN (
                'processing',
                'active',
                'inactive',
                'failed',
                'superseded'
            )
        ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE rag.chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL
        REFERENCES rag.documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    content TEXT NOT NULL CHECK (btrim(content) <> ''),
    embedding VECTOR(384) NOT NULL,
    embedding_model TEXT NOT NULL DEFAULT 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
        CHECK (embedding_model = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'),
    token_count INTEGER CHECK (token_count > 0),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(metadata) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_rag_chunks_document_index
        UNIQUE (document_id, chunk_index)
);

CREATE INDEX idx_rag_documents_retrieval_filters
    ON rag.documents (
        ticker,
        category,
        language,
        document_type,
        published_at DESC
    )
    WHERE status = 'active';

CREATE FUNCTION rag.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_rag_documents_updated_at
BEFORE UPDATE ON rag.documents
FOR EACH ROW
EXECUTE FUNCTION rag.set_updated_at();

COMMENT ON COLUMN rag.chunks.embedding IS
    '384-dimensional output from the local ONNX model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2, run by the rag service through fastembed. No embedding provider API key exists anywhere in this system. Changing the model or dimension requires a schema change, a full re-embed, and a rebuild of the optional vector index.';
