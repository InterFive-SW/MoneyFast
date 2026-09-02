"""Korpustaki HTML işaretlemesini temizler ve etkilenen parçaları yeniden gömer.

Neden var: ingestor haber özetini korpusa `content` olarak gönderiyordu ve RSS
özetleri işaretlemeyi olduğu gibi taşıyor. Ölçüldü -- 1.533 haber parçasının
**887'si** (%58) `<img align="right" ...>`, `<div>`, `&#039;` gibi içerik
taşıyordu. Bu, gömme vektörlerinin haberin metni yerine HTML gürültüsünü de
temsil etmesi demek: aramanın kalitesi doğrudan bundan düşüyor.

Kaynak `ingestor/sources/rss_source.py:clean_summary` içinde düzeltildi, yani
bundan sonra gelen her haber temiz geliyor. Bu betik yalnızca o düzeltmeden
önce toplanmış arşiv için.

SİLMİYOR, TEMİZLİYOR. Kirli belgeleri silmek 887 haberi korpustan çıkarmak
olurdu ve ingestor onları geri getirmez -- yalnızca beslemede o an duran
haberleri çeker. Metin temizlenip YENİDEN GÖMÜLÜYOR, böylece korpus hem
korunuyor hem düzeliyor.

Belge hash'i de güncelleniyor: korpus `sha256(content)` üzerinden tekilliyor,
dolayısıyla hash eski kirli metinde kalsaydı aynı haber ileride temiz hâliyle
yeniden alındığında ikinci bir kopya olarak yazılırdı.

    docker compose exec rag python -m scripts.clean_markup --dry-run
    docker compose exec rag python -m scripts.clean_markup --apply
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import re
import sys

import embeddings
import store

#: `ingestor/sources/rss_source.py`'daki ile aynı. Kopya, çünkü iki ayrı
#: servis ve aralarında paylaşılan kod yok -- backend'in ve rag'ın purge
#: betikleri de aynı sebeple bölüm listesini kopyalıyor.
_HTML_TAG = re.compile(r"<[^>]*>")

#: Bir parçayı kirli sayan desen. Varlıklar da dahil: `&#039;` metne
#: karıştığında gömme onu bir "kelime" gibi görüyor.
_DIRTY = r"<[a-zA-Z/][^>]*>|&#[0-9]{2,5};|&[a-zA-Z]{2,8};"


def clean(raw: str) -> str:
    """`rss_source.clean_summary` ile aynı davranış."""
    text = _HTML_TAG.sub(" ", raw or "")
    # İki geçiş: beslemeler çift kaçışlı gönderiyor (`LPG&amp;#039;nin`).
    for _ in range(2):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    return re.sub(r"\s+", " ", text).strip()


async def run(apply: bool) -> int:
    """Temizlenen parça sayısını döner."""
    pool = await store.open_pool()
    changed = removed = 0
    try:
        async with pool.connection() as conn:
            result = await conn.execute(
                """
                SELECT c.id AS chunk_id, d.id AS document_id, c.content,
                       d.published_at
                FROM rag.chunks c
                JOIN rag.documents d ON d.id = c.document_id
                WHERE c.content ~ %s
                ORDER BY d.published_at NULLS LAST, d.id
                """,
                (_DIRTY,),
            )
            rows = await result.fetchall()
            print(f"işaretleme taşıyan parça: {len(rows)}")

            # Hâlihazırda kullanılan hash'ler: temiz gelmiş belgeler ve bu
            # koşuda tutulacaklar. Bir temizlik sonucu bunlardan biriyle
            # çakışırsa elimizde bir KOPYA var demektir.
            # Kamusal korpusun tamamı. `owner_user_id` sütunu bu kurulumun
            # şemasında yok -- özel belge özelliği koda girmiş ama migration
            # uygulanmamış; burada her belge kamusal.
            taken = await conn.execute("SELECT content_hash, id FROM rag.documents")
            hashes = {r["content_hash"]: r["id"] for r in await taken.fetchall()}

            keep, duplicates = [], []
            for row in rows:
                cleaned = clean(row["content"])
                if not cleaned or cleaned == row["content"]:
                    continue
                digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
                owner = hashes.get(digest)
                if owner is not None and owner != row["document_id"]:
                    # Aynı haberin ikinci kopyası; işaretleme farkı onları
                    # ayrı göstermiş. Korpusta iki kez durmasının tek etkisi
                    # aramanın aynı haberi iki kez döndürmesi.
                    duplicates.append(row["document_id"])
                    continue
                hashes[digest] = row["document_id"]
                keep.append((row["chunk_id"], row["document_id"], cleaned, digest))

            print(f"temizlenecek: {len(keep)} | işaretleme ardında gizlenmiş kopya: {len(duplicates)}")
            for _, _, cleaned, _ in keep[:5]:
                print(f"  -> {cleaned[:90]}")

            if not apply:
                print("\n(deneme) hiçbir şey yazılmadı")
                return len(keep)

            # Gömme toplu yapılıyor: model çağrısı parça başına değil, bir
            # kerede. Dokuz yüz ayrı çağrı bunu dakikalar süren bir işe
            # çevirirdi.
            vectors = embeddings.embed_passages([text for _, _, text, _ in keep])
            for (chunk_id, document_id, cleaned, digest), vector in zip(keep, vectors):
                await conn.execute(
                    """
                    UPDATE rag.chunks
                    SET content = %s, embedding = %s::vector, token_count = %s
                    WHERE id = %s
                    """,
                    (cleaned, embeddings.to_pgvector(vector),
                     max(1, len(cleaned.split())), chunk_id),
                )
                # Tekillik `sha256(content)` üzerinden: hash eski kirli
                # metinde kalsaydı aynı haber temiz hâliyle yeniden alındığında
                # ikinci bir kopya olarak yazılırdı.
                await conn.execute(
                    "UPDATE rag.documents SET content_hash = %s WHERE id = %s",
                    (digest, document_id),
                )
                changed += 1

            if duplicates:
                await conn.execute(
                    "DELETE FROM rag.chunks WHERE document_id = ANY(%s)", (duplicates,)
                )
                await conn.execute(
                    "DELETE FROM rag.documents WHERE id = ANY(%s)", (duplicates,)
                )
                removed = len(duplicates)

        print(f"\ntemizlenip yeniden gömülen: {changed} | silinen kopya: {removed}")
        return changed
    finally:
        await store.close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    sys.exit(0 if asyncio.run(run(args.apply)) >= 0 else 1)
