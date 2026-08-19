\set ON_ERROR_STOP on

BEGIN;

INSERT INTO rag.documents (
    id,
    title,
    source,
    source_url,
    category,
    language,
    ticker,
    document_type,
    period,
    published_at,
    content_hash,
    status
)
VALUES
    (
        '00000000-0000-0000-0000-000000000101',
        'THYAO active report',
        'TEST-KAP',
        'https://example.invalid/thyao-active',
        'company-report',
        'tr',
        'THYAO',
        'annual-report',
        '2025',
        '2026-01-10T00:00:00Z',
        repeat('a', 64),
        'active'
    ),
    (
        '00000000-0000-0000-0000-000000000102',
        'THYAO older active report',
        'TEST-KAP',
        'https://example.invalid/thyao-old',
        'company-report',
        'tr',
        'THYAO',
        'annual-report',
        '2024',
        '2025-01-10T00:00:00Z',
        repeat('b', 64),
        'active'
    ),
    (
        '00000000-0000-0000-0000-000000000103',
        'THYAO inactive report',
        'TEST-KAP',
        'https://example.invalid/thyao-inactive',
        'company-report',
        'tr',
        'THYAO',
        'annual-report',
        '2023',
        '2024-01-10T00:00:00Z',
        repeat('c', 64),
        'inactive'
    ),
    (
        '00000000-0000-0000-0000-000000000104',
        'ASELS active report',
        'TEST-KAP',
        'https://example.invalid/asels-active',
        'company-report',
        'tr',
        'ASELS',
        'annual-report',
        '2025',
        '2026-01-10T00:00:00Z',
        repeat('d', 64),
        'active'
    );

INSERT INTO rag.chunks (
    id,
    document_id,
    chunk_index,
    content,
    embedding,
    embedding_model,
    token_count
)
VALUES
    (
        '00000000-0000-0000-0000-000000000201',
        '00000000-0000-0000-0000-000000000101',
        0,
        'THYAO exact match',
        (ARRAY[1::real] || array_fill(0::real, ARRAY[1535]))::vector,
        'text-embedding-3-small',
        3
    ),
    (
        '00000000-0000-0000-0000-000000000202',
        '00000000-0000-0000-0000-000000000102',
        0,
        'THYAO weaker match',
        (
            ARRAY[0.8::real, 0.6::real]
            || array_fill(0::real, ARRAY[1534])
        )::vector,
        'text-embedding-3-small',
        3
    ),
    (
        '00000000-0000-0000-0000-000000000203',
        '00000000-0000-0000-0000-000000000103',
        0,
        'Inactive document match',
        (ARRAY[1::real] || array_fill(0::real, ARRAY[1535]))::vector,
        'text-embedding-3-small',
        3
    ),
    (
        '00000000-0000-0000-0000-000000000204',
        '00000000-0000-0000-0000-000000000104',
        0,
        'ASELS exact match',
        (ARRAY[1::real] || array_fill(0::real, ARRAY[1535]))::vector,
        'text-embedding-3-small',
        3
    );

DO $$
DECLARE
    query_vector VECTOR(1536) :=
        (ARRAY[1::real] || array_fill(0::real, ARRAY[1535]))::vector;
    result_count INTEGER;
    first_chunk UUID;
BEGIN
    SELECT count(*), min(chunk_id)
    INTO result_count, first_chunk
    FROM rag.match_chunks(
        query_vector,
        5,
        NULL,
        'THYAO',
        'company-report',
        'tr',
        'annual-report',
        '2025-06-01T00:00:00Z'
    );

    IF result_count <> 1
       OR first_chunk <> '00000000-0000-0000-0000-000000000201' THEN
        RAISE EXCEPTION 'retrieval filters did not isolate the expected chunk';
    END IF;

    SELECT chunk_id
    INTO first_chunk
    FROM rag.match_chunks(query_vector, 2)
    WHERE ticker = 'THYAO'
    LIMIT 1;

    IF first_chunk <> '00000000-0000-0000-0000-000000000201' THEN
        RAISE EXCEPTION 'cosine similarity ordering is incorrect';
    END IF;
END;
$$;

UPDATE rag.documents
SET title = 'THYAO active report updated',
    updated_at = '2000-01-01T00:00:00Z'
WHERE id = '00000000-0000-0000-0000-000000000101';

DO $$
BEGIN
    IF (
        SELECT updated_at <= '2000-01-01T00:00:00Z'
        FROM rag.documents
        WHERE id = '00000000-0000-0000-0000-000000000101'
    ) THEN
        RAISE EXCEPTION 'updated_at trigger did not refresh the timestamp';
    END IF;
END;
$$;

DO $$
BEGIN
    BEGIN
        INSERT INTO rag.documents (
            title,
            source,
            category,
            language,
            document_type,
            content_hash
        )
        VALUES (
            'Duplicate hash',
            'TEST',
            'education',
            'tr',
            'guide',
            repeat('a', 64)
        );
        RAISE EXCEPTION 'duplicate content_hash was accepted';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO rag.chunks (
            document_id,
            chunk_index,
            content,
            embedding,
            embedding_model
        )
        VALUES (
            '00000000-0000-0000-0000-000000000101',
            0,
            'Duplicate chunk',
            (ARRAY[1::real] || array_fill(0::real, ARRAY[1535]))::vector,
            'text-embedding-3-small'
        );
        RAISE EXCEPTION 'duplicate document/chunk_index was accepted';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;

    BEGIN
        PERFORM * FROM rag.match_chunks(
            (ARRAY[1::real] || array_fill(0::real, ARRAY[1535]))::vector,
            21
        );
        RAISE EXCEPTION 'invalid top_k was accepted';
    EXCEPTION WHEN invalid_parameter_value THEN
        NULL;
    END;

    BEGIN
        PERFORM * FROM rag.match_chunks(
            (ARRAY[1::real] || array_fill(0::real, ARRAY[1535]))::vector,
            5,
            1.1
        );
        RAISE EXCEPTION 'invalid similarity threshold was accepted';
    EXCEPTION WHEN invalid_parameter_value THEN
        NULL;
    END;
END;
$$;

DELETE FROM rag.documents
WHERE id = '00000000-0000-0000-0000-000000000104';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM rag.chunks
        WHERE document_id = '00000000-0000-0000-0000-000000000104'
    ) THEN
        RAISE EXCEPTION 'document delete did not cascade to chunks';
    END IF;
END;
$$;

ROLLBACK;
