"""Arşivdeki KAP bildirimlerini `FILING` olarak yeniden türler.

Neden var: `ingestor` korpusa yazarken `document_type`'ı "NEWS" sabitliyordu.
Ölçüldü -- korpustaki 858 KAP belgesinin TAMAMI `NEWS` yazıyordu, yani "şirket
şunu bildirdi" ile "bir gazete şunu yazdı" ayırt edilemiyordu ve aramanın
`doc_types` süzgeci bu ayrımı hiç göremiyordu.

Kaynak `ingestor/sinks.py:_document_type` içinde düzeltildi; bundan sonra gelen
her bildirim doğru türle geliyor. Bu betik yalnızca o düzeltmeden önce
toplanmış arşiv için.

YENİDEN GÖMME YOK. Değişen tek şey bir metadata sütunu; parçanın içeriği ve
vektörü aynı kalıyor, dolayısıyla arama sonuçları değişmiyor -- yalnızca
`doc_types` süzgeci artık bu belgeleri görüyor.

`FILING`, sözleşmenin donuk `doc_types` kümesinde ZATEN vardı; yeni bir tür
icat etmek dondurulmuş bir alana belgelenmemiş bir değer koymak olurdu.

    docker compose exec rag python -m scripts.retype_filings --dry-run
    docker compose exec rag python -m scripts.retype_filings --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import store

#: Bildirim yayımlayan kaynaklar. `ingestor/sinks.py:FILING_SOURCES` ile aynı
#: liste. Kopya, çünkü iki ayrı servis ve aralarında paylaşılan kod yok --
#: temizlik betiklerinin bölüm listelerini kopyalamasıyla aynı sebep.
FILING_SOURCES = ("KAP",)

FILING_TYPE = "FILING"


async def run(apply: bool) -> int:
    """Yeniden türlenen belge sayısını döner."""
    pool = await store.open_pool()
    try:
        async with pool.connection() as conn:
            result = await conn.execute(
                """
                SELECT count(*) AS n
                FROM rag.documents
                WHERE source = ANY(%s) AND document_type IS DISTINCT FROM %s
                """,
                (list(FILING_SOURCES), FILING_TYPE),
            )
            rows = await result.fetchall()
            count = rows[0]["n"]
            print(f"yanlış türlenmiş bildirim: {count}", file=sys.stderr)

            if not apply:
                print("(deneme) hiçbir şey yazılmadı", file=sys.stderr)
                return count

            await conn.execute(
                """
                UPDATE rag.documents SET document_type = %s
                WHERE source = ANY(%s) AND document_type IS DISTINCT FROM %s
                """,
                (FILING_TYPE, list(FILING_SOURCES), FILING_TYPE),
            )
        print(f"yeniden türlenen: {count}", file=sys.stderr)
        return count
    finally:
        await store.close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    sys.exit(0 if asyncio.run(run(args.apply)) >= 0 else 1)
