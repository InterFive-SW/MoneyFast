#!/bin/sh
set -eu

export LC_ALL=C

migrations_dir="${1:-/migrations/base}"

if [ ! -d "$migrations_dir" ]; then
    echo "Migration directory does not exist: $migrations_dir" >&2
    exit 2
fi

calculate_sha256() {
    migration_file="$1"

    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$migration_file" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$migration_file" | awk '{print $1}'
    elif command -v openssl >/dev/null 2>&1; then
        openssl dgst -sha256 "$migration_file" | awk '{print $NF}'
    else
        echo "No SHA-256 implementation is available." >&2
        return 4
    fi
}

psql -X -v ON_ERROR_STOP=1 <<'SQL'
CREATE SCHEMA IF NOT EXISTS rag_migrations;

CREATE TABLE IF NOT EXISTS rag_migrations.schema_migrations (
    version TEXT PRIMARY KEY,
    checksum CHAR(64) NOT NULL
        CHECK (checksum ~ '^[0-9a-f]{64}$'),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by TEXT NOT NULL DEFAULT current_user
);

REVOKE ALL ON SCHEMA rag_migrations FROM PUBLIC;
REVOKE ALL ON TABLE rag_migrations.schema_migrations FROM PUBLIC;
SQL

found_migration=false

for migration in "$migrations_dir"/[0-9][0-9][0-9][0-9]_*.sql; do
    if [ ! -f "$migration" ]; then
        continue
    fi

    found_migration=true
    version="$(basename "$migration" .sql)"

    case "$version" in
        *[!a-zA-Z0-9_-]*)
            echo "Unsafe migration filename: $version" >&2
            exit 2
            ;;
    esac

    checksum="$(calculate_sha256 "$migration")"

    if ! printf '%s\n' "$checksum" |
        awk 'length($0) == 64 && $0 ~ /^[0-9a-f]+$/ { valid = 1 } END { exit !valid }'
    then
        echo "Invalid SHA-256 output for migration: $version" >&2
        exit 4
    fi

    applied_checksum="$(
        psql -X -A -t -v ON_ERROR_STOP=1 -v version="$version" <<'SQL'
SELECT checksum
FROM rag_migrations.schema_migrations
WHERE version = :'version';
SQL
    )"

    if [ -n "$applied_checksum" ]; then
        if [ "$applied_checksum" != "$checksum" ]; then
            echo "Checksum mismatch for applied migration: $version" >&2
            exit 3
        fi
        echo "Skipping applied migration: $version"
        continue
    fi

    echo "Applying migration: $version"
    {
        printf '%s\n' '\set ON_ERROR_STOP on' 'BEGIN;'
        printf '\\echo Applying %s\n' "$version"
        printf '%s\n' "\\i $migration"
        printf '%s\n' \
            "INSERT INTO rag_migrations.schema_migrations (version, checksum)" \
            "VALUES (:'version', :'checksum');" \
            'COMMIT;'
    } | psql -X \
        -v ON_ERROR_STOP=1 \
        -v version="$version" \
        -v checksum="$checksum"
done

if [ "$found_migration" != true ]; then
    echo "No migration files found in: $migrations_dir" >&2
    exit 2
fi

echo "Vector migrations are up to date."
