"""Commit'lenmiş haber derlemini açılışta yükler.

Derlem RSS'ten geliyor ve gömülmesi yerel CPU zamanı istiyor; yeni bir klon
açıldığında "Şu an gösterilecek haber yok" görüyor ve sohbetin arayabileceği
hiçbir şey olmuyor. Bu dosya o boşluğun ZEMİNİ -- ingestor'ın yerine
geçmiyor, RSS turu üstüne yazmaya devam ediyor.

**Vektörler dosyadan geliyor, yeniden hesaplanmıyor.** `fastembed` yerelde
çalışıyor, yani klon gömmeleri kendisi de üretebilirdi; bu, ilk açılışta bayt
bayt aynı sonuç için harcanan CPU zamanı olurdu.

**Sahipsiz yazılır.** Belgeler herkese açık derleme giriyor
(`owner_user_id IS NULL`). Bir sahip atansaydı iki türlü de yanlış olurdu:
dışa aktaranın id'si klonda kimseye ait değil ve belgeler görünmez olurdu;
klonun ilk kullanıcısına atansa ortak haber derlemi bir kişinin özel
dosyaları olurdu.

Her açılışta çalışması güvenli: `content_hash` üzerindeki kısmi tekil indeks
ikinci yüklemede hiçbir şey yazdırmıyor.
"""

from __future__ import annotations

import csv
import gzip
import io
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("moneyfast.rag.seed")

SEED_FILE = Path(os.getenv("MARKET_SEED_DIR") or "/seeds/market") / "corpus.csv.gz"

DOCUMENT_FIELDS = (
    "title", "source", "source_url", "category", "language", "ticker",
    "document_type", "period", "published_at", "content_hash",
)


def _grouped(path: Path) -> dict[str, dict[str, Any]]:
    """Satırları belgeye göre toplar. Bir belge birden çok parça taşıyabilir."""
    documents: dict[str, dict[str, Any]] = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            clean = {k: (v if v != "" else None) for k, v in row.items()}
            key = clean["content_hash"]
            entry = documents.setdefault(
                key,
                {"document": {f: clean[f] for f in DOCUMENT_FIELDS}, "chunks": []},
            )
            entry["chunks"].append(
                (int(clean["chunk_index"]), clean["content"], clean["embedding"])
            )
    return documents


async def load(open_pool) -> int:
    """Derlemi yükler; YAZILAN belge sayısını döner.

    Hiçbir koşulda açılışı düşürmez: eksik dosya, bozuk satır ya da
    erişilemeyen veritabanı bir uyarı bırakır ve servis normal başlar.
    Aranacak haber olmaması, hiç açılmamaktan iyidir.
    """
    if not SEED_FILE.exists():
        log.info("corpus seed not found at %s; nothing to load", SEED_FILE)
        return 0

    try:
        documents = _grouped(SEED_FILE)
    except Exception as exc:
        log.warning("corpus seed unreadable: %s", exc)
        return 0

    written = 0
    try:
        pool = await open_pool()
        async with pool.connection() as conn:
            for entry in documents.values():
                async with conn.transaction():
                    cursor = await conn.execute(
                        """
                        INSERT INTO rag.documents (
                            title, source, source_url, category, language,
                            ticker, document_type, period, published_at,
                            content_hash, owner_user_id
                        )
                        VALUES (
                            %(title)s, %(source)s, %(source_url)s, %(category)s,
                            %(language)s, %(ticker)s, %(document_type)s,
                            %(period)s, %(published_at)s, %(content_hash)s, NULL
                        )
                        ON CONFLICT (content_hash) WHERE owner_user_id IS NULL
                        DO NOTHING
                        RETURNING id
                        """,
                        entry["document"],
                    )
                    row = await cursor.fetchone()
                    if row is None:
                        # Zaten var. Parçaları yeniden yazmak, aynı içeriğin
                        # iki kopyasının aynı arama sırasında yarışması olurdu.
                        continue
                    document_id = row["id"]
                    for index, content, embedding in entry["chunks"]:
                        await conn.execute(
                            """
                            INSERT INTO rag.chunks (
                                document_id, chunk_index, content, embedding
                            )
                            VALUES (%(doc)s, %(idx)s, %(content)s, %(vec)s::vector)
                            """,
                            {
                                "doc": document_id, "idx": index,
                                "content": content, "vec": embedding,
                            },
                        )
                    written += 1
    except Exception as exc:
        log.warning("corpus seed load failed: %s", exc)
        return written

    log.info("corpus seed: %d of %d documents written", written, len(documents))
    return written
