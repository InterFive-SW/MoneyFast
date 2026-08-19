#!/bin/sh
set -eu

psql_bin="${PSQL_BIN:-psql}"

if [ -n "${RAG_DB_PASSWORD_FILE:-}" ]; then
    if [ ! -r "$RAG_DB_PASSWORD_FILE" ]; then
        echo "RAG password file is not readable." >&2
        exit 2
    fi
    RAG_DB_PASSWORD="$(cat "$RAG_DB_PASSWORD_FILE")"
    export RAG_DB_PASSWORD
fi

if [ -z "${RAG_DB_USER:-}" ]; then
    echo "RAG_DB_USER is required." >&2
    exit 2
fi

if [ -z "${RAG_DB_PASSWORD:-}" ]; then
    echo "RAG_DB_PASSWORD or RAG_DB_PASSWORD_FILE is required." >&2
    exit 2
fi

"$psql_bin" -X -v ON_ERROR_STOP=1 -f /bootstrap/vector-db-grants.sql
