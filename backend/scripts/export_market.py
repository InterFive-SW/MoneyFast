"""Piyasa verisini `seeds/market/` altına dışa aktarır.

Neden var: fiyat, mum ve temel veri ingestor'ın açılıştan SONRA ürettiği
şeyler. Ölçülen tam tur ~9 dakika ve sağlayıcı kota uyguluyor; bu ikisi
yüzünden yeni bir klon, açıldığı ilk dakikalarda sektörü "Bilinmiyor", piyasa
değeri "0 $" ve grafikleri boş bir uygulama gösteriyor. Bu dosyalar o
boşluğun ZEMİNİ: ingestor yerine geçmiyor, ona üstüne çıkacağı bir taban
veriyor.

CLAUDE.md mumların bir dönem commit'lendiğini (7,5 MB) ve ingestor onları
kendisi çekebildiği için kaldırıldığını yazıyor. Mekanizma hâlâ doğru;
eksik olan tabandı.

**Sembol yazılır, id ASLA.** Enstrüman id'leri migration içinde
`gen_random_uuid()` ile üretiliyor, yani her makinede farklı; id taşıyan bir
satır başkasının veritabanında foreign key hatası verir. `seeds/users/*.sql`
zaten bu kurala uyuyor.

Çıktı gzip'li CSV. Ölçülen: iki yıllık günlük bar 9,3 MB (SQL INSERT olarak
aynı veri kat kat büyük), temel veri 32 KB.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402

#: Kaç yıllık günlük bar. İki, çünkü portföy performans grafiğinin en uzun
#: aralığı "2 YIL" ve daha kısası o düğmeyi ilk açılışta boş bırakırdı.
HISTORY_YEARS = 2

#: Çıktı dizini. Repo kökündeki `seeds/market/`; kapta çalıştırılırken
#: `MARKET_SEED_DIR` ile başka bir yere yazdırılabiliyor.
OUT_DIR = Path(
    os.getenv("MARKET_SEED_DIR")
    or Path(__file__).resolve().parents[2] / "seeds" / "market"
)

FUNDAMENTAL_COLUMNS = (
    "pe_ratio", "pb_ratio", "market_cap", "dividend_yield", "sector", "industry",
    "week52_high", "week52_low", "total_revenue", "revenue_growth",
    "gross_margin", "operating_margin", "ebitda_margin", "profit_margin",
    "return_on_equity", "return_on_assets", "debt_to_equity", "current_ratio",
    "total_debt", "total_cash", "free_cash_flow", "operating_cash_flow",
    "enterprise_value", "beta", "trailing_eps", "forward_eps", "forward_pe",
    "earnings_growth", "payout_ratio", "dividend_rate", "recommendation_key",
    "analyst_count", "target_mean_price", "ex_dividend_date", "earnings_date",
)


def _write(path: Path, header: tuple, rows) -> int:
    """Gzip'li CSV yaz. Satır sayısını döner."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    count = 0
    for row in rows:
        writer.writerow(row)
        count += 1
    # `mtime=0`: gzip başlığı yazma zamanını taşıyor ve o zaman her çalıştırmada
    # değişiyor. Verisi aynı olan bir dışa aktarma AYNI baytları üretmeli,
    # yoksa her export git'te tam bir yeniden yazma gibi görünür -- kullanıcı
    # başına ayırmanın önlediği çakışmanın ta kendisi.
    path.write_bytes(gzip.compress(buffer.getvalue().encode("utf-8"), 9, mtime=0))
    return count


def export_fundamentals(db) -> int:
    rows = db.execute(text(f"""
        SELECT p.symbol, {", ".join("f." + c for c in FUNDAMENTAL_COLUMNS)}
        FROM investment.instrument_fundamentals f
        JOIN investment.investment_products p ON p.id = f.product_id
        ORDER BY p.symbol
    """)).all()
    return _write(OUT_DIR / "fundamentals.csv.gz", ("symbol", *FUNDAMENTAL_COLUMNS), rows)


def export_candles(db) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=365 * HISTORY_YEARS)
    rows = db.execute(text("""
        SELECT p.symbol, c.timestamp, c.open_price, c.high_price,
               c.low_price, c.close_price, c.volume
        FROM investment.market_candles c
        JOIN investment.investment_products p ON p.id = c.product_id
        WHERE c.interval = '1d' AND c.timestamp >= :since
        ORDER BY p.symbol, c.timestamp
    """), {"since": since}).all()
    return _write(
        OUT_DIR / "candles.csv.gz",
        ("symbol", "timestamp", "open", "high", "low", "close", "volume"),
        rows,
    )


#: Kaç aylık KAP bildirimi dışa aktarılır.
NEWS_MONTHS = int(os.getenv("SEED_NEWS_MONTHS", "6"))

#: Dışa aktarılan haber kaynakları. Yalnızca KAP: RSS haberleri kısa ömürlü
#: ve besleme listesi kurulumdan kuruluma değişebiliyor, dolayısıyla bir
#: klonun "haber" diye altı ay önceki manşetleri göstermesi doğru olmaz.
#: Bildirim ise tarihli bir kayıttır ve eskimez.
NEWS_SOURCES = ("KAP",)


def export_news(db) -> int:
    """Bildirim BAŞLIKLARI -- gövdeler değil.

    Gövdeler ve ekleri kasten dışarıda. Ölçülen: altı ay ~28.900 bildirim;
    gövdeleriyle ve gömme vektörleriyle birlikte bu, git'e onlarca megabayt
    demek. Başlık, ihraççı, tarih ve kalıcı bağlantı ise sıkıştırıldığında
    birkaç megabayt ve klonun ilk açılışında ANLAMLI olan tam da o: Piyasa
    Haberleri dolu geliyor, her satırın hisse etiketi ve çalışan bir
    `kap.org.tr` bağlantısı oluyor.

    Gövdeler ingestor tarafından çalışma anında indiriliyor. Bu bir eksiklik
    değil, iş bölümü: pano tarihsel bir kayıt istiyor, korpus ise okunacak
    metin -- ve ikincisi git'te taşınacak şey değil.
    """
    since = datetime.now(timezone.utc) - timedelta(days=30 * NEWS_MONTHS)
    rows = db.execute(text("""
        SELECT content_hash, title, summary, source, url, language,
               array_to_string(related_symbols, ' '), published_at
        FROM market.news_items
        WHERE source = ANY(:sources) AND published_at >= :since
        ORDER BY published_at, content_hash
    """), {"sources": list(NEWS_SOURCES), "since": since}).all()
    return _write(
        OUT_DIR / "news.csv.gz",
        ("content_hash", "title", "summary", "source", "url", "language",
         "related_symbols", "published_at"),
        rows,
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        funds = export_fundamentals(db)
        candles = export_candles(db)
        news = export_news(db)
    finally:
        db.close()

    # Künye: yükleyici bununla "zaten dolu" diyebiliyor.
    #
    # Onsuz her yeniden başlatma 505 bin satırı geçici tabloya kopyalayıp
    # hiçbir şey yazmadan atıyordu -- ölçülen 30 saniye, her açılışta,
    # tamamen boşuna. Beklenen satır sayısını dışa aktaran biliyor.
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(
            {"fundamentals": funds, "candles": candles, "news": news}, indent=2
        ) + "\n",
        encoding="utf-8",
    )
    for name in ("fundamentals.csv.gz", "candles.csv.gz", "news.csv.gz"):
        size = (OUT_DIR / name).stat().st_size
        print(f"  {name:22s} {size / 1024 / 1024:6.2f} MB")
    print(f"  temel veri {funds} satır, mum {candles} satır, bildirim {news} satır")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
