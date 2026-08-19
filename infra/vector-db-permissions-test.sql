\set ON_ERROR_STOP on
\getenv rag_user RAG_DB_USER

SELECT set_config('moneyfast.test_rag_user', :'rag_user', false);

DO $$
DECLARE
    role_name TEXT := current_setting('moneyfast.test_rag_user', true);
BEGIN
    IF role_name IS NULL OR role_name = '' THEN
        RAISE EXCEPTION 'moneyfast.test_rag_user is required';
    END IF;

    IF NOT has_schema_privilege(role_name, 'rag', 'USAGE') THEN
        RAISE EXCEPTION 'RAG role is missing schema usage';
    END IF;

    IF has_schema_privilege(role_name, 'rag', 'CREATE') THEN
        RAISE EXCEPTION 'RAG role can create objects in rag schema';
    END IF;

    IF has_schema_privilege(role_name, 'rag_migrations', 'USAGE') THEN
        RAISE EXCEPTION 'RAG role can access migration ledger schema';
    END IF;

    IF NOT has_database_privilege(role_name, current_database(), 'CONNECT') THEN
        RAISE EXCEPTION 'RAG role cannot connect to the vector database';
    END IF;

    IF has_database_privilege(role_name, current_database(), 'TEMPORARY') THEN
        RAISE EXCEPTION 'RAG role can create temporary objects';
    END IF;

    IF NOT has_table_privilege(
        role_name,
        'rag.documents',
        'SELECT,INSERT,UPDATE,DELETE'
    ) THEN
        RAISE EXCEPTION 'RAG role is missing document DML privileges';
    END IF;

    IF has_table_privilege(role_name, 'rag.documents', 'TRUNCATE') THEN
        RAISE EXCEPTION 'RAG role can truncate documents';
    END IF;

    IF NOT has_function_privilege(
        role_name,
        'rag.match_chunks(vector,integer,double precision,text,text,text,text,timestamptz)',
        'EXECUTE'
    ) THEN
        RAISE EXCEPTION 'RAG role cannot execute retrieval';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles
        WHERE rolname = role_name
          AND (
              rolsuper
              OR rolcreatedb
              OR rolcreaterole
              OR rolreplication
          )
    ) THEN
        RAISE EXCEPTION 'RAG role has privileged role attributes';
    END IF;
END;
$$;
