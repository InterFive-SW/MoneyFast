"""Haber derlemini `seeds/market/corpus.csv.gz` olarak dışa aktarır.

Neden var: derlem RSS'ten geliyor ve gömülmesi yerel CPU zamanı istiyor. Yeni
bir klon açıldığında "Şu an gösterilecek haber yok" görüyor ve sohbetin
arayabileceği hiçbir şey olmuyor. Bu dosya o boşluğun zemini.

**Vektörler de taşınıyor.** `fastembed` yerelde çalışıyor, yani klon
gömmeleri kendisi de üretebilirdi -- ama bu, ilk açılışta bayt bayt aynı
sonuç için harcanan CPU zamanı demek.

**Sahip alanı YAZILMAZ.** Dışa aktarılan belgeler herkese açık derlem
(`owner_user_id IS NULL`). Sahibi yazılsaydı iki türlü de yanlış olurdu:
dışa aktaranın id'si klonda kimseye ait olmaz ve belgeler görünmez; klonun
ilk kullanıcısına atansa ortak haber derlemi bir kişinin özel dosyaları
olurdu. Bu yüzden sorgu `owner_user_id IS NULL` ile SÜZÜLÜYOR -- birinin
yüklediği bir bilanço, ekibe dağıtılan bir dosyaya sızmamalı.
"""

from __future__ import annotations

import asyncio
import csv
import gzip
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store  # noqa: E402

OUT = Path(os.getenv("MARKET_SEED_DIR") or "/seeds/market") / "corpus.csv.gz"

COLUMNS = (
    "title", "source", "source_url", "category", "language", "ticker",
    "document_type", "period", "published_at", "content_hash",
    "chunk_index", "content", "embedding",
)


async def export() -> int:
    pool = await store.open_pool()
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            SELECT d.title, d.source, d.source_url, d.category, d.language,
                   d.ticker, d.document_type, d.period, d.published_at,
                   d.content_hash, c.chunk_index, c.content,
                   c.embedding::text AS embedding
            FROM rag.documents d
            JOIN rag.chunks c ON c.document_id = d.id
            WHERE d.owner_user_id IS NULL AND d.status = 'active'
            ORDER BY d.content_hash, c.chunk_index
            """
        )
        rows = await cursor.fetchall()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow([row[c] for c in COLUMNS])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # `mtime=0`: verisi aynı olan bir dışa aktarma AYNI baytları üretmeli,
    # yoksa her export git'te tam bir yeniden yazma gibi görünür.
    OUT.write_bytes(gzip.compress(buffer.getvalue().encode("utf-8"), 9, mtime=0))
    return len(rows)


def main() -> int:
    count = asyncio.run(export())
    print(f"  corpus.csv.gz  {OUT.stat().st_size / 1024 / 1024:5.2f} MB  ({count} parça)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
