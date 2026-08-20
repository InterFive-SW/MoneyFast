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

    -- The `rag_migrations` ledger no longer exists: schema setup moved to
    -- Postgres' own /docker-entrypoint-initdb.d/ mechanism, so there is no
    -- ledger left to keep the application role out of. What still matters is
    -- that the role cannot plant objects outside `rag`.
    IF has_schema_privilege(role_name, 'public', 'CREATE') THEN
        RAISE EXCEPTION 'RAG role can create objects in the public schema';
    END IF;

    -- No DIRECT grant on public either. This is what vector-db-grants.sql's
    -- `REVOKE ALL ON SCHEMA public FROM <rag_user>` actually controls.
    --
    -- Note that has_schema_privilege(role, 'public', 'USAGE') is still TRUE,
    -- and deliberately not asserted against: PostgreSQL grants USAGE on
    -- `public` to the PUBLIC pseudo-role by default (`=U/pg_database_owner`
    -- in nspacl), and a REVOKE naming the role cannot remove a grant made to
    -- PUBLIC. Removing it would need
    -- `REVOKE USAGE ON SCHEMA public FROM PUBLIC`, which affects every role in
    -- the database, not just this one. There is nothing in `public` here, so
    -- it is recorded rather than changed.
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_namespace
        WHERE nspname = 'public'
          AND array_to_string(nspacl, ',') LIKE '%' || role_name || '=%'
    ) THEN
        RAISE EXCEPTION 'RAG role holds a direct grant on the public schema';
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
        'rag.match_chunks(vector,integer,double precision,text[],text[],text[],text[],timestamptz,timestamptz,text[])',
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
