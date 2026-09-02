"""Arşivdeki haberlerin çözülmüş sembollerini adresleriyle birlikte dışa aktarır.

Neden var: eşleştirme burada, enstrüman evreninin bulunduğu yerde yapılıyor ve
`rag` servisi evreni tutmuyor -- tutmamalı da, veritabanı kredensiyeli
taşımıyor ve backend'e giden bir yolu yok. Bu ayrım bilinçli, dolayısıyla
haritayı taşımanın yolu yeni bir bağımlılık değil, iki komut:

    docker compose exec -T backend python -m scripts.export_news_symbols > /tmp/map.json
    docker compose exec -T rag python -m scripts.backfill_tickers --apply < /tmp/map.json

Yalnızca ARŞİV için. `ingestor` artık çözülen sembolleri `news/ingest`
yanıtından alıp RAG'a yazdığı için bundan sonra gelen her haber etiketli
geliyor; bu betik, o düzeltmeden önce toplanmış 1.970 belge için.

Anahtar `source_url`: iki depo aynı haberi farklı hash'lerle tanıyor
(backend metnin tamamını, RAG parçanın içeriğini hash'liyor) ve ortak
tanımlayıcı adres.
"""

from __future__ import annotations

import json
import sys

from app.core.database import SessionLocal
from app.modules.market.models import NewsItem


def build() -> dict[str, list[str]]:
    """`source_url` -> semboller. Etiketsiz ve adressiz haberler dışarıda."""
    db = SessionLocal()
    try:
        rows = (
            db.query(NewsItem.url, NewsItem.related_symbols)
            .filter(NewsItem.url.isnot(None))
            .order_by(NewsItem.published_at)
            .all()
        )
    finally:
        db.close()
    return {url: list(symbols) for url, symbols in rows if url and symbols}


if __name__ == "__main__":
    mapping = build()
    print(f"{len(mapping)} haber için sembol bulundu", file=sys.stderr)
    json.dump(mapping, sys.stdout, ensure_ascii=False)
