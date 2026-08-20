\set ON_ERROR_STOP on
\getenv rag_user RAG_DB_USER
\getenv rag_password RAG_DB_PASSWORD

\if :{?rag_user}
\else
    \echo 'rag_user variable is required'
    \quit 3
\endif

\if :{?rag_password}
\else
    \echo 'rag_password variable is required'
    \quit 3
\endif

SELECT
    nullif(btrim(:'rag_user'), '') IS NULL AS rag_user_is_empty,
    nullif(:'rag_password', '') IS NULL AS rag_password_is_empty
\gset

\if :rag_user_is_empty
    \echo 'RAG_DB_USER must not be empty'
    \quit 3
\endif

\if :rag_password_is_empty
    \echo 'RAG_DB_PASSWORD must not be empty'
    \quit 3
\endif

SELECT :'rag_user' = current_user AS rag_user_is_admin
\gset

\if :rag_user_is_admin
    \echo 'rag_user must differ from the vector database administrator'
    \quit 3
\endif

BEGIN;

SELECT format('CREATE ROLE %I LOGIN', :'rag_user')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :'rag_user'
)
\gexec

SELECT format('ALTER ROLE %I PASSWORD %L', :'rag_user', :'rag_password')
\gexec

SELECT format(
    'ALTER ROLE %I NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
    :'rag_user'
)
\gexec

SELECT format(
    'REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC',
    current_database()
)
\gexec

SELECT format(
    'GRANT CONNECT ON DATABASE %I TO %I',
    current_database(),
    :'rag_user'
)
\gexec

SELECT format('REVOKE ALL ON SCHEMA public FROM %I', :'rag_user')
\gexec

REVOKE ALL ON SCHEMA rag FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA rag FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA rag FROM PUBLIC;

SELECT format('GRANT USAGE ON SCHEMA rag TO %I', :'rag_user')
\gexec

SELECT format(
    'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rag TO %I',
    :'rag_user'
)
\gexec

SELECT format(
    'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA rag TO %I',
    :'rag_user'
)
\gexec

SELECT format(
    'GRANT EXECUTE ON FUNCTION rag.match_chunks(vector, integer, double precision, text[], text[], text[], text[], timestamptz, timestamptz, text[]) TO %I',
    :'rag_user'
)
\gexec

REVOKE EXECUTE ON FUNCTION rag.match_chunks(
    vector,
    integer,
    double precision,
    text[],
    text[],
    text[],
    text[],
    timestamptz,
    timestamptz,
    text[]
) FROM PUBLIC;

SELECT format(
    'ALTER DEFAULT PRIVILEGES IN SCHEMA rag GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
    :'rag_user'
)
\gexec

SELECT format(
    'ALTER DEFAULT PRIVILEGES IN SCHEMA rag GRANT USAGE, SELECT ON SEQUENCES TO %I',
    :'rag_user'
)
\gexec

ALTER DEFAULT PRIVILEGES IN SCHEMA rag
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

COMMIT;
