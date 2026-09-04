"""Korpustaki etiketsiz haber belgelerine backend'in çözdüğü sembolü yazar.

Neden var: `ticker` alanı belgeye yazılırken `ingestor`'ın kendi etiket
listesinden geliyordu ve RSS beslemeleri etiket vermiyor. Eşleştirme
backend'de yapılıyor ama sonucu geri dönmüyordu, dolayısıyla korpustaki kopya
etiketsiz kalıyordu. Ölçüldü: 1.970 RSS belgesinin **sıfırında** ticker vardı,
yani ajanın `tickers` filtresi yalnızca KAP bildirimlerinde çalışıyordu --
onlar etiketi kaynağından getirdiği için.

Kaynak `ingestor/sinks.py` ve `market/service.py:upsert_news` içinde
düzeltildi; bundan sonra gelen her haber etiketli geliyor. Bu betik yalnızca
o düzeltmeden önce toplanmış arşiv için.

Harita backend'den geliyor, çünkü enstrüman evreni orada ve bu servisin
backend'e giden bir yolu YOK -- olması da istenmiyor, `rag` bir yaprak servis.
İki komut:

    docker compose exec -T backend python -m scripts.export_news_symbols > /tmp/map.json
    docker compose exec -T rag python -m scripts.backfill_tickers --dry-run < /tmp/map.json
    docker compose exec -T rag python -m scripts.backfill_tickers --apply   < /tmp/map.json

YENİDEN GÖMME YOK. Değişen tek şey bir metadata sütunu; parçanın içeriği ve
vektörü aynı kalıyor, dolayısıyla arama sonuçları değişmiyor -- yalnızca
`tickers` filtresi artık bu belgeleri görüyor.

Dolu bir `ticker` ÜSTÜNE YAZILMIYOR: KAP bildirimleri etiketi kaynağından
getiriyor ve kaynağın kendi beyanını metinden çıkarılmış bir eşleşmeyle
değiştirmek geriye gidiş olurdu.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import store


async def run(mapping: dict[str, list[str]], apply: bool) -> int:
    """Etiketlenen belge sayısını döner."""
    pool = await store.open_pool()
    try:
        async with pool.connection() as conn:
            result = await conn.execute(
                """
                SELECT id, source_url
                FROM rag.documents
                WHERE ticker IS NULL AND source_url IS NOT NULL
                """
            )
            rows = await result.fetchall()
            print(f"etiketsiz belge: {len(rows)}", file=sys.stderr)

            # Belge başına TEK sembol: korpus şeması tek bir ticker sütunu
            # taşıyor. Birden fazla şirkete dokunan haber ilkini saklar ve
            # gerisi metinden bulunabilir kalır.
            updates = [
                (mapping[row["source_url"]][0], row["id"])
                for row in rows
                if mapping.get(row["source_url"])
            ]
            print(f"eşleşen: {len(updates)}", file=sys.stderr)

            if not apply:
                print("(deneme) hiçbir şey yazılmadı", file=sys.stderr)
                return len(updates)

            for ticker, document_id in updates:
                await conn.execute(
                    "UPDATE rag.documents SET ticker = %s WHERE id = %s",
                    (ticker, document_id),
                )
        print(f"etiketlenen: {len(updates)}", file=sys.stderr)
        return len(updates)
    finally:
        await store.close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    sys.exit(0 if asyncio.run(run(json.load(sys.stdin), args.apply)) >= 0 else 1)
