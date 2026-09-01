#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

# After the migrations, never before: the seed files reference instruments the
# migrations create. Non-fatal on purpose -- a seed problem must not be the
# reason the API will not start.
echo "Loading seed data..."
python -m scripts.load_seeds || echo "seed load failed; continuing without it"

# Piyasa verisinin TABANI: temel veri ve iki yıllık günlük bar.
#
# Bunları ingestor üretiyor ama açılıştan sonra ve ölçülen tam tur ~9 dakika;
# sağlayıcı da kota uyguluyor. O pencerede yeni bir klon sektörü "Bilinmiyor",
# piyasa değeri "0 $" ve grafikleri boş gösteriyordu. Yükleme ingestor'ın
# yerine geçmiyor -- ingestor bu tabanın üstünden devam ediyor.
echo "Loading market seed..."
python -m scripts.load_market || echo "market seed failed; continuing without it"

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
