"""Haber arşivini onarır: işaretlemeyi temizler ve sembollere bağlar.

Tek seferlik. Sembol çözümlemesi `market/service.py:upsert_news` içinde, yani
bundan sonra gelen her haber yazılırken bağlanıyor -- bu betik yalnızca o
kod yokken toplanmış arşiv için.

Ölçüldü: çalıştırıldığı anda veritabanında 1.540 haber vardı ve **hiçbirinin**
`related_symbols`'ü dolu değildi. Alan baştan beri şemadaydı; onu dolduran
tek yol RSS `<category>` etiketleriydi ve yapılandırılmış beslemelerin
hiçbiri kategori etiketi yayımlamıyor.

Yalnızca BOŞ olanlara dokunur. Kaynağın kendi verdiği bir etiket -- ileride
KAP bildirimleri böyle gelecek -- metinden çıkarımla ezilmez.

Aynı koşuda özetlerdeki HTML de temizleniyor. RSS özetleri işaretlemeyi
olduğu gibi taşıyor ve bu metin hem eşleştirmeye hem ekrana gidiyor;
ölçüldü, 1.548 haberin 922'sinde `<img align="right" ...>` benzeri içerik
vardı. Kaynak `rss_source.clean_summary` içinde düzeltildi, bu betik arşiv
için. `content_hash` DEĞİŞMİYOR: kimlik ham metinden hesaplanıyor ve onu
değiştirmek arşivin tamamını "yeni" saydırırdı.

    docker compose exec backend python -m scripts.backfill_news_symbols
    docker compose exec backend python -m scripts.backfill_news_symbols --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.core.database import SessionLocal
from app.modules.investment.models import InvestmentProduct
from app.modules.market import service as news_service, symbol_match
from app.modules.market.models import NewsItem

log = logging.getLogger("moneyfast.backfill")


def run(dry_run: bool = False) -> int:
    """Bağlanan haber sayısını döner."""
    session = SessionLocal()
    try:
        universe = (
            session.query(InvestmentProduct)
            .filter(InvestmentProduct.product_type == "stock")
            .all()
        )
        rows = (
            session.query(NewsItem)
            .filter(NewsItem.related_symbols == [])
            .order_by(NewsItem.published_at.desc())
            .all()
        )
        print(f"evren: {len(universe)} hisse | bağlanmamış haber: {len(rows)}")

        # Önce TÜM satırlarda işaretleme temizliği: bağlanmamış olanlarla
        # sınırlı kalsaydı, bağlı bir haberin özeti ekranda HTML olarak
        # kalırdı.
        cleaned_count = 0
        for row in session.query(NewsItem).all():
            if not row.summary:
                continue
            cleaned = symbol_match.strip_markup(row.summary)
            if cleaned and cleaned != row.summary:
                if not dry_run:
                    row.summary = cleaned
                cleaned_count += 1
        print(f"işaretlemesi temizlenen özet: {cleaned_count}")

        linked = 0
        for row in rows:
            text = " ".join(filter(None, (row.title, row.summary)))
            # Ingest yolunun ta kendisi: politika tek yerde.
            found = news_service.resolve_news_symbols(text, universe)
            if not found:
                continue
            linked += 1
            if linked <= 15:
                labels = ", ".join(f"{f['symbol']}/{f['basis']}" for f in found)
                print(f"  {labels:28} {row.title[:64]}")
            if not dry_run:
                row.related_symbols = [f["symbol"] for f in found]

        if dry_run:
            session.rollback()
        else:
            session.commit()
        share = 100 * linked / len(rows) if rows else 0.0
        print(
            f"\n{'(deneme) ' if dry_run else ''}bağlanan: {linked}/{len(rows)} "
            f"(%{share:.1f})"
        )
        return linked
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Neyin bağlanacağını yazar, veritabanına yazmaz.",
    )
    sys.exit(0 if run(parser.parse_args().dry_run) >= 0 else 1)
