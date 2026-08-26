#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

# After the migrations, never before: the seed files reference instruments the
# migrations create. Non-fatal on purpose -- a seed problem must not be the
# reason the API will not start.
echo "Loading seed data..."
python -m scripts.load_seeds || echo "seed load failed; continuing without it"

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
