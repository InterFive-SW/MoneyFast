"""`seeds/market/` altındaki piyasa verisini yükler.

Her backend açılışında, `load_seeds.py`'nin hemen ardından çalışıyor. Sıra
tesadüf değil: bu dosyalar `investment.investment_products` satırlarına
SEMBOLLE bağlanıyor ve o satırları migration'lar kuruyor.

**Neden var.** Fiyat, mum ve temel veri ingestor'ın açılıştan sonra ürettiği
şeyler; ölçülen tam tur ~9 dakika ve sağlayıcı kota uyguluyor. Yeni bir klon
o pencerede sektörü "Bilinmiyor", piyasa değeri "0 $" ve grafikleri boş bir
uygulama gösteriyor. Bu yükleme ingestor'ın yerine geçmiyor -- ona üstüne
çıkacağı bir taban veriyor, ve ingestor kaldığı yerden devam ediyor.

**Sembolle bağlanır, id ile değil.** Enstrüman id'leri her makinede farklı
(`gen_random_uuid()`); id taşıyan bir satır başkasının veritabanında foreign
key hatası verirdi.

**Her açılışta çalışması güvenli.** İki tablo da `ON CONFLICT DO NOTHING`
ile yazılıyor, dolayısıyla ikinci çalıştırma tek bir tarama maliyetiyle
hiçbir şey yazmıyor. Eksik ya da boş bir `seeds/market/` hata DEĞİL: dosyalar
commit'lenmeden önceki hâl budur ve uygulama yine de açılmak zorunda.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import logging
import os
from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionLocal

log = logging.getLogger("moneyfast.load_market")

SEED_DIR = Path(os.getenv("MARKET_SEED_DIR") or "/app/seeds/market")

#: Temel veri için tek bir INSERT'e kaç satır. Bin satırlık bir tabloda
#: parçalama yeterli; mumlar (505 bin) COPY ile gidiyor, çünkü satır satır
#: INSERT orada ölçülen 135 saniyeydi ve o süre boyunca backend açılmıyordu.
CHUNK = 2_000

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


def _rows(path: Path):
    """Gzip'li CSV'yi sözlük olarak okur. Boş hücre `None` olur.

    CSV boş hücre ile boş metni ayırt etmiyor ve bizim için fark büyük:
    `''` bir sayı sütununa yazılamaz ve bir marj sütununda 0 diye okunabilir.
    """
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            yield {k: (v if v != "" else None) for k, v in row.items()}


def _expected() -> dict[str, int]:
    """Dışa aktarmanın yazdığı satır sayıları.

    Künye yoksa boş dönüyor ve her şey yüklenmeyi dener -- eski bir dump ile
    açılan bir klonda doğru davranış bu.
    """
    path = SEED_DIR / "manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _already_loaded(db, table: str, expected: int, where: str = "") -> bool:
    """Tabloda beklenen kadar satır var mı.

    Bu kontrol olmadan her yeniden başlatma 505 bin satırı geçici tabloya
    kopyalayıp hiçbir şey yazmadan atıyordu: ölçülen 30 saniye, her açılışta.

    Eşitlik değil "en az" karşılaştırması: ingestor dump'ın üstüne yazmaya
    devam ediyor, dolayısıyla dolu bir veritabanında satır sayısı beklenenden
    BÜYÜK olur. Küçükse yükleme yarım kalmış demektir ve tekrar denenmeli.
    """
    if not expected:
        return False
    count = db.execute(
        text(f"SELECT count(*) FROM {table} {where}")
    ).scalar() or 0
    return count >= expected


def _symbol_ids(db) -> dict[str, str]:
    return {
        symbol: str(pid)
        for symbol, pid in db.execute(
            text("SELECT symbol, id FROM investment.investment_products")
        ).all()
    }


def load_fundamentals(db, ids: dict[str, str], expected: int = 0) -> int:
    path = SEED_DIR / "fundamentals.csv.gz"
    if not path.exists():
        return 0
    if _already_loaded(db, "investment.instrument_fundamentals", expected):
        return 0
    payload = []
    for row in _rows(path):
        product_id = ids.get(row["symbol"])
        if product_id is None:
            # Bu klonun evreninde olmayan bir sembol. Sessizce atlanıyor:
            # migration'lar evreni değiştirdiğinde dump'ın eskimesi normal.
            continue
        payload.append({"pid": product_id, **{c: row[c] for c in FUNDAMENTAL_COLUMNS}})

    written = 0
    columns = ", ".join(FUNDAMENTAL_COLUMNS)
    values = ", ".join(f":{c}" for c in FUNDAMENTAL_COLUMNS)
    for start in range(0, len(payload), CHUNK):
        batch = payload[start:start + CHUNK]
        db.execute(
            text(f"""
                INSERT INTO investment.instrument_fundamentals
                    (id, product_id, {columns}, updated_at)
                VALUES (gen_random_uuid(), :pid, {values}, now())
                ON CONFLICT ON CONSTRAINT uq_instrument_fundamentals_product
                DO NOTHING
            """),
            batch,
        )
        written += len(batch)
    db.commit()
    return written


def load_candles(db, ids: dict[str, str], expected: int = 0) -> int:
    """Mumları geçici tabloya COPY edip tek ifadeyle aktarır.

    Satır satır INSERT ile ÖLÇÜLDÜ: 505.563 bar 135 saniye sürüyordu ve o
    süre boyunca backend hiç açılmıyor -- giriş bile yapılamayan iki dakikalık
    bir bekleme, boş ekranlardan daha kötü bir ilk açılış.

    COPY doğrudan `ON CONFLICT` kabul etmiyor, o yüzden iki adım: geçici
    tabloya dök, sonra tek `INSERT ... SELECT ... ON CONFLICT DO NOTHING`.
    Tekrar çalıştırıldığında yine hiçbir şey yazmıyor.

    Semboller SQL'e hiç girmiyor -- eşleme Python tarafında yapılıyor ve
    COPY'ye yalnızca çözülmüş `product_id` gidiyor.
    """
    path = SEED_DIR / "candles.csv.gz"
    if not path.exists():
        return 0
    if _already_loaded(
        db, "investment.market_candles", expected, "WHERE \"interval\" = '1d'"
    ):
        return 0

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    count = 0
    for row in _rows(path):
        product_id = ids.get(row["symbol"])
        if product_id is None:
            continue
        writer.writerow([
            product_id, row["timestamp"], row["open"], row["high"],
            row["low"], row["close"], row["volume"],
        ])
        count += 1
    if not count:
        return 0

    buffer.seek(0)
    raw = db.connection().connection
    with raw.cursor() as cursor:
        cursor.execute("""
            CREATE TEMP TABLE _seed_candles (
                product_id UUID, ts TIMESTAMPTZ,
                o NUMERIC, h NUMERIC, l NUMERIC, c NUMERIC, v BIGINT
            ) ON COMMIT DROP
        """)
        cursor.copy_expert(
            "COPY _seed_candles FROM STDIN WITH (FORMAT csv)", buffer
        )
        cursor.execute("""
            INSERT INTO investment.market_candles
                (id, product_id, "interval", timestamp, open_price,
                 high_price, low_price, close_price, volume, source)
            SELECT gen_random_uuid(), product_id, '1d', ts, o, h, l, c, v, 'seed'
            FROM _seed_candles
            ON CONFLICT ON CONSTRAINT uq_market_candles_bar DO NOTHING
        """)
    db.commit()
    return count


def main() -> int:
    if not SEED_DIR.exists():
        log.info("market seed directory not found at %s; nothing to load", SEED_DIR)
        return 0

    db = SessionLocal()
    try:
        ids = _symbol_ids(db)
        if not ids:
            log.warning("no instruments yet; market seed skipped")
            return 0
        expected = _expected()
        funds = load_fundamentals(db, ids, expected.get("fundamentals", 0))
        candles = load_candles(db, ids, expected.get("candles", 0))
    finally:
        db.close()

    log.info("market seed offered: %d fundamentals, %d candles", funds, candles)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
