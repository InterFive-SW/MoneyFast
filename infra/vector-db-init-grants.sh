#!/bin/sh
# Application-role bootstrap, run once by the Postgres entrypoint from
# /docker-entrypoint-initdb.d/ after the schema files (10-, 20-, 30-) have
# been applied.
#
# Successor to the deleted run-vector-bootstrap.sh. The validation and grant
# logic still lives in vector-db-grants.sql; this file only resolves the
# password source and points psql at the right cluster.
#
# Two things differ from running under the old vector-migrations container:
#
#   * There is no PGHOST/PGUSER/PGDATABASE in the environment. The entrypoint
#     exports POSTGRES_USER and POSTGRES_DB, and during initialisation the
#     server listens on the unix socket only, so a local superuser connection
#     needs no password.
#   * The script may be sourced rather than executed when the file loses its
#     exec bit on checkout. `set -u` is therefore deliberately not used: it
#     would leak into the entrypoint shell and abort the boot on the next
#     unset variable it reads.

set -e

if [ -n "${RAG_DB_PASSWORD_FILE:-}" ]; then
    if [ ! -r "$RAG_DB_PASSWORD_FILE" ]; then
        echo "RAG password file is not readable: $RAG_DB_PASSWORD_FILE" >&2
        exit 2
    fi
    RAG_DB_PASSWORD="$(cat "$RAG_DB_PASSWORD_FILE")"
    export RAG_DB_PASSWORD
fi

if [ -z "${RAG_DB_USER:-}" ]; then
    echo "RAG_DB_USER is required on the vector-db service." >&2
    exit 2
fi

if [ -z "${RAG_DB_PASSWORD:-}" ]; then
    echo "RAG_DB_PASSWORD or RAG_DB_PASSWORD_FILE is required on the vector-db service." >&2
    exit 2
fi

# Read by psql through \getenv, never passed as a process argument, so the
# secret never appears in the container's process list.
export RAG_DB_USER RAG_DB_PASSWORD

PGUSER="${POSTGRES_USER}"
PGDATABASE="${POSTGRES_DB}"
export PGUSER PGDATABASE

psql -X -v ON_ERROR_STOP=1 -f /bootstrap/vector-db-grants.sql
