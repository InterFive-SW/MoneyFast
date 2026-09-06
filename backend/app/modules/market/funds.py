"""Fon listesi ve fiyat serisi.

`Fonlar` ekranı `MOCK_FUNDS` üzerinden çiziliyordu ve üstünde "Örnek veri"
uyarısı vardı. Burası onun arkasındaki gerçek veri.

**Süzgeçler SUNUCUDA.** Evren 2.602 fon; hepsini tarayıcıya gönderip orada
süzmek, her açılışta birkaç yüz kilobayt ve süzgeç mantığının ikinci bir
kopyası demekti.

**Getiriler burada HESAPLANIYOR, saklanmıyor.** `fund_prices` NAV serisini
tutuyor ve yüzde ondan türetiliyor. Saklamak, aynı sayının iki yerde
yaşaması ve serinin güncellendiği ama yüzdenin güncellenmediği bir aralık
bırakması olurdu.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .models import Fund, FundPrice

#: Getiri pencereleri: arayüzdeki sütunların karşılığı.
#:
#: Takvim günü, işlem günü değil: NAV yalnızca iş günlerinde yayımlanıyor ve
#: "1 ay" kullanıcı için otuz gün demek, yirmi iki bar değil.
RETURN_WINDOWS: dict[str, int] = {
    "daily": 1, "monthly": 30, "threeMonth": 90,
    "yearly": 365, "threeYear": 1095, "fiveYear": 1825,
}

#: Tek istekte dönebilecek en fazla fon.
MAX_LIMIT = 500


def upsert_funds(db: Session, rows: Sequence[dict[str, Any]]) -> int:
    """Fon satırlarını yazar; var olanı günceller.

    Kısmi güncelleme: gelen sözlükte OLMAYAN alan mevcut değerini koruyor.
    Evren turu şemsiye türünü taşımıyor, günlük tur kurucuyu taşımıyor -- her
    turun diğerinin alanlarını `NULL`la ezmesi, iki turu birbirinin işini
    bozar hâle getirirdi.
    """
    written = 0
    for row in rows:
        code = str(row.get("code") or "").strip().upper()
        if not code:
            continue
        values = {k: v for k, v in row.items() if k != "code" and v is not None}
        if not values:
            continue

        # ÖNCE güncelleme, sonra ekleme.
        #
        # `INSERT ... ON CONFLICT DO UPDATE` burada çalışmıyor: Postgres
        # önerilen satırın NOT NULL kısıtlarını çatışmayı çözmeden ÖNCE
        # denetliyor. Ölçüldü -- şemsiye türü güncellemesi (`{code,
        # umbrella}`) satır zaten dururken bile şu hatayı verdi:
        #
        #   null value in column "title" of relation "funds"
        #   violates not-null constraint
        #
        # Yani kısmi güncelleme, tam bir satır göndermeden mümkün değildi.
        result = db.execute(
            update(Fund).where(Fund.code == code).values(**values)
        )
        if result.rowcount:
            written += 1
            continue

        # Satır yok: ancak adı da biliyorsak ekleyebiliriz. Adsız bir fon
        # eklemek, listede boş bir satır üretirdi.
        if not values.get("title"):
            continue
        db.execute(insert(Fund).values(code=code, **values))
        written += 1
    return written


#: Fonun enstrüman evrenindeki karşılığı. `data_symbol` BOŞ: yfinance bir
#: TEFAS fon kodunu fiyatlayamaz ve boş bırakmak "bunu fiyatlamaya çalışma"
#: demek (bkz. `InvestmentProduct.data_symbol`). Fiyat `market.funds`tan
#: geliyor.
FUND_PRODUCT_TYPE = "fund"
FUND_MARKET = "TEFAS"

#: TEFAS fiyatının `market_quotes` satırındaki kaynağı. Sağlayıcı adı
#: kullanıcıya çıkmıyor (`sanitize.py`), ama hangi beslemenin yazdığı
#: kayıtta durmalı.
FUND_QUOTE_SOURCE = "TEFAS_DAILY"


def ensure_tradable(db: Session, code: str):
    """Bir fonu, İHTİYAÇ DUYULDUĞUNDA enstrüman evrenine yazar.

    Emirler, pozisyonlar, portföy değerlemesi ve risk yollarının HEPSİ
    `investment.investment_products` üzerinden geçiyor. Fonlar ayrı bir
    tabloda durduğu sürece "fon al" diye bir yol yoktu; paralel bir fon-emri
    yolu yazmak ise `settle`i ikinci kez yazmak olurdu.

    **Toptan değil, tek tek.** 2.602 fonu evrene yazmak, Piyasalar ekranını
    ve enstrüman listesini kimsenin aramadığı fon kodlarıyla doldururdu --
    Fonlar ekranı zaten var ve orası fonların yeri. Burası yalnızca gerçekten
    işlem gören fonu köprülüyor.

    Var olan bir enstrüman satırına DOKUNMUYOR: aynı kodu taşıyan bir hisse
    buradan sessizce ezilmemeli.
    """
    from app.modules.investment.models import InvestmentProduct

    code = (code or "").strip().upper()
    if not code:
        return None
    existing = db.execute(
        select(InvestmentProduct).where(InvestmentProduct.symbol == code)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    fund = db.get(Fund, code)
    if fund is None or not fund.active:
        return None

    product = InvestmentProduct(
        symbol=code,
        data_symbol=None,
        name=fund.title,
        product_type=FUND_PRODUCT_TYPE,
        market=FUND_MARKET,
        currency_code="TRY",
        status="active",
    )
    db.add(product)
    db.flush()
    sync_quotes(db, [code])
    # İkinci `flush` ŞART: oturum `autoflush=False` ile kuruluyor
    # (`core/database.py`), dolayısıyla `sync_quotes`un yazdığı kotasyon
    # aynı istek içinde bir SELECT'e görünmüyor. Ölçüldü -- fonun ilk emri
    # "Fiyat bilgisi bulunamayan enstrüman: GRO" ile reddediliyordu, oysa
    # fiyat o anda yazılmıştı.
    db.flush()
    return product


def sync_quotes(db: Session, codes: Optional[Sequence[str]] = None) -> int:
    """İşlem gören fonların NAV'ını `market_quotes`a yansıtır.

    **Tek fiyat kuralı:** portföy değerlemesi, pozisyon satırı ve risk
    hesabının hepsi `investment.market_quotes`tan okuyor. Fon fiyatını orada
    yazmamak, satın alınmış bir fon pozisyonunun değerinin boş görünmesi
    demekti.

    Yalnızca evrende KARŞILIĞI OLAN fonlar yazılıyor -- yani birilerinin
    işlem yaptığı fonlar. Bütün fonlara kotasyon açmak, Piyasalar ekranındaki
    her listeye 2.602 satır eklerdi.

    `change_percent` bir önceki NAV'dan hesaplanıyor; ikinci bir gün yoksa
    NULL kalıyor. Sıfır yazmak, "gün içinde değişmedi" iddiası olurdu.
    """
    from app.modules.investment.models import InvestmentProduct, MarketQuote

    query = select(InvestmentProduct.id, InvestmentProduct.symbol).where(
        InvestmentProduct.product_type == FUND_PRODUCT_TYPE
    )
    if codes is not None:
        query = query.where(InvestmentProduct.symbol.in_([c.upper() for c in codes]))
    products = db.execute(query).all()
    if not products:
        return 0

    funds = {
        fund.code: fund
        for fund in db.execute(
            select(Fund).where(Fund.code.in_([symbol for _, symbol in products]))
        ).scalars()
    }
    written = 0
    for product_id, symbol in products:
        fund = funds.get(symbol)
        if fund is None or fund.price is None or fund.as_of is None:
            continue
        series = price_series(db, symbol, limit=2)
        previous = float(series[0].price) if len(series) > 1 else None
        price = float(fund.price)
        change = None if previous in (None, 0) else price - previous
        db.merge(
            MarketQuote(
                id=f"fundq:{symbol}",
                product_id=product_id,
                price=price,
                change_amount=change,
                change_percent=(
                    None if change is None else round(change / previous * 100, 4)
                ),
                previous_close=previous,
                volume=None,
                # NAV'ın kendi günü. Gün içi bir zaman damgası uydurmak,
                # olmayan bir anlık fiyatı varmış gibi göstermek olurdu.
                market_timestamp=datetime.combine(
                    fund.as_of, time(0, 0), tzinfo=timezone.utc
                ),
                received_at=datetime.now(timezone.utc),
                source=FUND_QUOTE_SOURCE,
            )
        )
        written += 1
    return written


def upsert_prices(db: Session, rows: Sequence[dict[str, Any]]) -> int:
    """NAV serisini yazar. Aynı gün ikinci kez yazılırsa fiyat güncellenir.

    `DO NOTHING` DEĞİL: TEFAS bir günün fiyatını sonradan düzeltebiliyor ve
    ilk yazılanı korumak, düzeltilmiş bir fiyatı reddetmek olurdu.
    """
    payload = []
    for row in rows:
        code = str(row.get("code") or "").strip().upper()
        as_of = row.get("as_of")
        price = row.get("price")
        if not code or not as_of or price is None:
            continue
        payload.append({"code": code, "as_of": as_of, "price": price})
    if not payload:
        return 0
    statement = insert(FundPrice).values(payload)
    db.execute(statement.on_conflict_do_update(
        index_elements=[FundPrice.code, FundPrice.as_of],
        set_={"price": statement.excluded.price},
    ))
    return len(payload)


def list_funds(
    db: Session,
    founder: Optional[str] = None,
    umbrella: Optional[str] = None,
    fund_type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Fund]:
    """Süzülmüş fon listesi, büyükten küçüğe.

    Portföy büyüklüğüne göre sıralı: bir fon listesinin varsayılan sırası
    alfabe olsaydı, ekranın ilk ekranı kimsenin aramadığı fonlarla dolardı.
    Büyüklüğü bilinmeyen fon SONA gidiyor, sıfır sayılmıyor.
    """
    query = select(Fund).where(Fund.active.is_(True))
    if founder:
        query = query.where(Fund.founder == founder)
    if umbrella:
        query = query.where(Fund.umbrella == umbrella)
    if fund_type:
        query = query.where(Fund.fund_type == fund_type.upper())
    if search:
        needle = f"%{search.strip().lower()}%"
        query = query.where(
            Fund.title.ilike(needle) | Fund.code.ilike(needle)
        )
    query = query.order_by(Fund.size.desc().nullslast(), Fund.code)
    return list(db.execute(query.limit(limit).offset(offset)).scalars())


def facets(db: Session) -> dict[str, list[str]]:
    """Süzgeç açılır listelerinin içeriği — VERİDEN, elle yazılmış değil.

    Elle yazılmış bir liste, TEFAS yeni bir kurucu eklediğinde sessizce
    eksik kalırdı.
    """
    founders = db.execute(
        select(Fund.founder).where(Fund.founder.isnot(None)).distinct().order_by(Fund.founder)
    ).scalars()
    umbrellas = db.execute(
        select(Fund.umbrella).where(Fund.umbrella.isnot(None)).distinct().order_by(Fund.umbrella)
    ).scalars()
    return {"founders": list(founders), "umbrellas": list(umbrellas)}


def price_series(db: Session, code: str, limit: int = 400) -> list[FundPrice]:
    """Bir fonun NAV serisi, eskiden yeniye."""
    rows = db.execute(
        select(FundPrice)
        .where(FundPrice.code == code.strip().upper())
        .order_by(FundPrice.as_of.desc())
        .limit(limit)
    ).scalars()
    return sorted(rows, key=lambda row: row.as_of)


def returns_for(series: Sequence[FundPrice]) -> dict[str, Optional[float]]:
    """Pencere başına yüzde getiri; hesaplanamayan pencere `None`.

    `None` ile sıfır AYRI: "bu fonun beş yıllık geçmişi yok" ile "beş yılda
    hiç kazandırmadı" karşıt iddialar ve arayüz ilkini `NA` diye yazıyor.

    Referans, pencerenin başına EŞİT YA DA ONDAN SONRAKİ ilk gözlem: NAV
    yalnızca iş günlerinde yayımlanıyor, dolayısıyla tam o günü aramak
    hafta sonuna denk gelen her pencereyi ölçülemez yapardı.
    """
    if not series:
        return {name: None for name in RETURN_WINDOWS}

    latest = series[-1]
    earliest = series[0]
    out: dict[str, Optional[float]] = {}
    for name, days in RETURN_WINDOWS.items():
        target = latest.as_of - timedelta(days=days)
        # Seri pencerenin BAŞINA kadar gitmiyorsa o pencere ölçülemiyor.
        #
        # Bu denetim olmadan iki günlük bir seri "yıllık getiri %1" diyordu:
        # en yakın gözlem olarak dünü alıp bir yıllık pencereye yazıyordu.
        # Bir günün getirisini bir yılın getirisi diye sunmak, yanlış bir
        # sayıdan daha kötü -- ölçek hatası.
        if earliest.as_of > target:
            out[name] = None
            continue
        reference = next((row for row in series if row.as_of >= target), None)
        # Referans en son gözlemin kendisiyse pencere ölçülemiyor.
        if reference is None or reference.as_of >= latest.as_of or not reference.price:
            out[name] = None
            continue
        out[name] = round(
            (float(latest.price) - float(reference.price)) / float(reference.price) * 100, 2
        )
    return out


def coverage(db: Session) -> dict[str, Any]:
    """Toplayıcının neyi eksik bıraktığını sorduğu yer.

    Şemsiye türü ve NAV serisi fon BAŞINA birer istek ve evren 2.602 fon;
    hangi fonların hâlâ eksik olduğunu bilmeden her tur baştan başlardı.
    """
    total = db.execute(select(Fund.code).where(Fund.active.is_(True))).scalars().all()
    missing_umbrella = db.execute(
        select(Fund.code).where(Fund.active.is_(True), Fund.umbrella.is_(None))
    ).scalars().all()
    priced = db.execute(select(FundPrice.code).distinct()).scalars().all()
    # Kategori sırası fiyat serisiyle AYNI yanıtta geliyor, ama seriyi
    # ölçüler eklenmeden önce çekilmiş fonlarda sıra boş kaldı. Onları
    # ayrıca listelemek, seriyi silip yeniden çekmekten ucuz.
    missing_category = db.execute(
        select(Fund.code).where(Fund.active.is_(True), Fund.category_rank.is_(None))
    ).scalars().all()
    priced_set = set(priced)
    return {
        "funds": len(total),
        "missing_umbrella": list(missing_umbrella),
        "missing_prices": [code for code in total if code not in priced_set],
        "missing_category": [code for code in missing_category if code in priced_set],
    }


# ── Mumlar ──────────────────────────────────────────────────────────────────

#: Aralık -> (kova, kaç gün geriye).
#:
#: Fon günde TEK fiyat yayımlıyor. Günlük bir mumun açılış/yüksek/düşük/
#: kapanışı aynı sayı olurdu -- yani mum değil, yassı bir çizgi. Gerçek bir
#: mum ancak birkaç gün KOVALANARAK çıkıyor: açılış = kovanın ilk NAV'ı,
#: yüksek/düşük = kova uçları, kapanış = son. Her değer ölçülmüş oluyor.
CANDLE_RANGES: dict[str, tuple[str, int]] = {
    "1A": ("week", 30),
    "3A": ("week", 90),
    "1Y": ("month", 365),
    "5Y": ("month", 1825),
}


def _bucket_key(day: date, bucket: str) -> date:
    """Bir günün ait olduğu kovanın başlangıcı."""
    if bucket == "month":
        return day.replace(day=1)
    # Haftanın pazartesisi.
    return day - timedelta(days=day.weekday())


def candles(db: Session, code: str, window: str = "3A") -> list[dict[str, Any]]:
    """Fonun NAV serisinden kovalanmış OHLC.

    Seri eskiden yeniye geliyor, dolayısıyla her kovanın ilk gördüğü satır
    açılış, sonuncusu kapanış.
    """
    bucket, days = CANDLE_RANGES.get(window) or CANDLE_RANGES["3A"]
    series = price_series(db, code, limit=2000)
    if not series:
        return []

    cutoff = series[-1].as_of - timedelta(days=days)
    buckets: dict[date, dict[str, Any]] = {}
    for row in series:
        if row.as_of < cutoff:
            continue
        key = _bucket_key(row.as_of, bucket)
        price = float(row.price)
        current = buckets.get(key)
        if current is None:
            buckets[key] = {
                "date": key, "open": price, "high": price,
                "low": price, "close": price,
            }
            continue
        current["high"] = max(current["high"], price)
        current["low"] = min(current["low"], price)
        current["close"] = price
    return [buckets[key] for key in sorted(buckets)]
