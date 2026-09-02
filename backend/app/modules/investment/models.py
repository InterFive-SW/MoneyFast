"""Investment ORM models.

Schema layout follows `infra/intertech.sql`, the reference design: these
tables live in the `investment` schema rather than `public`. The `users` table
predates that decision and stays in `public` until the auth owner moves it;
mixing the two is deliberate and temporary, not an oversight.

`investment_products` is the instrument universe. `symbol` is the ticker as
everyone writes it (`THYAO`, `AAPL`) and `data_symbol` is what the market data
provider knows it as (`THYAO.IS`). The `TEST-` prefix is gone: nobody types it,
and a chatbot that rejects "THYAO" because it only knows "TEST-THYAO" is not a
chatbot anyone can use.

What remains synthetic is the *account*, not the instrument: quantities and
cost bases in `portfolio_positions` are seeded, while every price, bar and
fundamental attached to them is real.
"""

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SCHEMA = "investment"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InvestmentProduct(Base):
    """One tradable instrument, and the symbol map for market data."""

    __tablename__ = "investment_products"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    #: Symbol as the rest of this system knows it, e.g. "TEST-THYAO".
    symbol: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    #: Symbol the data provider knows, e.g. "THYAO.IS". Nullable: an
    #: instrument with no upstream feed is legitimate, and a NULL here means
    #: "do not try to price this" rather than "price it as zero".
    data_symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_type: Mapped[str] = mapped_column(String(50), nullable=False, default="stock")
    market: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="TRY")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class MarketQuote(Base):
    """Current price for a product. Exactly ONE row per product.

    Overwritten on every ingest cycle rather than appended. At a ten-second
    cadence over ~95 instruments, append-only would add roughly 112,000 rows a
    day and make the latest-price lookup progressively slower, in exchange for
    a tick history nothing reads. History that IS read lives in
    `market_candles`.
    """

    __tablename__ = "market_quotes"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_market_quotes_product"),
        Index("idx_market_quotes_product_time", "product_id", "market_timestamp"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.investment_products.id", ondelete="CASCADE"), nullable=False
    )
    price: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    change_amount: Mapped[float | None] = mapped_column(Numeric(19, 4), nullable=True)
    change_percent: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    previous_close: Mapped[float | None] = mapped_column(Numeric(19, 4), nullable=True)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    #: When the price was true at the exchange. Distinct from received_at on
    #: purpose: the gap between them IS the delay the AI contract must
    #: disclose, and collapsing them would let stale data be presented live.
    market_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)


class MarketCandle(Base):
    """OHLCV bar. The price history every ex-post risk metric needs."""

    __tablename__ = "market_candles"
    __table_args__ = (
        UniqueConstraint("product_id", "interval", "timestamp", name="uq_market_candles_bar"),
        Index("idx_market_candles_product_interval_time", "product_id", "interval", "timestamp"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.investment_products.id", ondelete="CASCADE"), nullable=False
    )
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open_price: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    high_price: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    low_price: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    close_price: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)


class TransactionProposal(Base):
    """A staged, unconfirmed transaction.

    Deliberately separate from `investment_orders`. A proposal is short-lived,
    usually never confirmed, and carries no execution state; folding it into
    the orders table would mean a row that looks like an order but is not one,
    which is exactly the confusion the whole staging contract exists to
    prevent.

    It is also what makes the confirm endpoint verifiable: without a record,
    "does this proposal exist and has it expired" cannot be answered, and any
    proposal_id a client invents would be accepted.
    """

    __tablename__ = "transaction_proposals"
    __table_args__ = (
        Index("idx_transaction_proposals_user", "user_id", "created_at"),
        {"schema": SCHEMA},
    )

    #: The proposal_id returned to the agent, derived from the idempotency
    #: key, so a retried staging call resolves to this same row.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Numeric(19, 6), nullable=True)
    source_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False, default="MARKET")
    #: Full staged payload, so the confirm step presents exactly what was
    #: staged rather than re-deriving it from live prices that have moved.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audit_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class InstrumentQuarterly(Base):
    """Çeyreklik gelir tablosu. Enstrüman başına DÖNEM DÖNEM bir satır.

    `InstrumentFundamentals` bir anlık görüntü: alan başına tek güncel değer,
    geçmiş yok. Bu yüzden "son çeyrek kârı önceki çeyreğe göre şu kadar arttı"
    kurulamıyordu -- kıyaslanacak ikinci dönem hiç saklanmıyordu. Bu tablo o
    boşluğu kapatıyor ve iki tablo AYRI duruyor, çünkü biri her gün üstüne
    yazılıyor, diğeri birikiyor.

    DOĞAL ANAHTAR (product_id, period_end). Sıra numarası değil: sağlayıcının
    dönemleri ardışık gelmiyor -- ölçüldü, AKBNK/GARAN/EREGL'de 2025Q3 gelir
    tablosunda hiç yok. "Son iki satırı al" diyen bir karşılaştırma o üç
    hissede 2025Q2 ile 2025Q4'ü kıyaslar ve bunu söylemez; bitişiklik dönem
    sonundan hesaplanmak zorunda.

    Dört kalem saklanıyor. Sağlayıcının gelir tablosu şirkete göre 33-52 satır
    ve derin örneklenen on iki sembolün hepsinde bulunan yirmi kalemden
    yalnızca bunlar bu kartın sorusunu cevaplıyor. `Basic EPS` bilerek yok:
    34 hissede son çeyrekte 32 kez dolu, bir önceki çeyrekte YALNIZCA 3 kez --
    seri olarak saklamak neredeyse hep yarısı boş bir kolon açmak olurdu ve
    hisse başına kâr zaten anlık tabloda duruyor.

    Her sayısal kolon nullable. Ölçüldü: 34 hissenin 16'sında serinin bir
    yerinde eksik değer var, ve sıfıra çevirmek "o çeyrek raporlandı, kâr
    sıfır çıktı" demek olurdu.
    """

    __tablename__ = "instrument_quarterly"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "period_end", name="uq_instrument_quarterly_period"
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(
        String, ForeignKey(f"{SCHEMA}.investment_products.id"), nullable=False, index=True
    )
    #: Çeyreğin BİTİŞ tarihi, sağlayıcının verdiği hâliyle. Etiket
    #: ("2026Q2") saklanmıyor: tamamen bundan türetilebiliyor ve hiçbir zaman
    #: değişmeyecek bir değer için ikinci bir sütun, ikisinin ayrışabileceği
    #: bir yer açardı.
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    total_revenue: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    net_income: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pretax_income: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operating_expense: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class InstrumentFundamentals(Base):
    """Valuation ratios and company facts. One row per product, refreshed daily.

    Every numeric column is nullable and stays that way. Coverage from the
    provider is genuinely partial — THYAO has no trailing P/E while AAPL does —
    and defaulting a missing ratio to zero would make a stock with no earnings
    data look like the cheapest name on the screen.
    """

    __tablename__ = "instrument_fundamentals"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_instrument_fundamentals_product"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.investment_products.id", ondelete="CASCADE"), nullable=False
    )
    pe_ratio: Mapped[float | None] = mapped_column(Numeric(19, 4), nullable=True)
    pb_ratio: Mapped[float | None] = mapped_column(Numeric(19, 4), nullable=True)
    market_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(80), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    week52_high: Mapped[float | None] = mapped_column(Numeric(19, 4), nullable=True)
    week52_low: Mapped[float | None] = mapped_column(Numeric(19, 4), nullable=True)

    # Gelir tablosu ve kârlılık (migration 0027). Sağlayıcıdan zaten gelen ama
    # atılan alanlar; bunlar olmadan bir hissenin neye DEĞDİĞİ söylenebiliyor,
    # nasıl GİTTİĞİ söylenemiyordu.
    #
    # Oranlar kesir: 0,1287 = %12,87. Yüzdeye çevirmek gösterim katmanının işi.
    total_revenue: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    revenue_growth: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    gross_margin: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    operating_margin: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    ebitda_margin: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    profit_margin: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    return_on_equity: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    return_on_assets: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    debt_to_equity: Mapped[float | None] = mapped_column(Numeric(19, 4), nullable=True)
    current_ratio: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    total_debt: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_cash: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    free_cash_flow: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operating_cash_flow: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    enterprise_value: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    beta: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    trailing_eps: Mapped[float | None] = mapped_column(Numeric(19, 4), nullable=True)
    forward_eps: Mapped[float | None] = mapped_column(Numeric(19, 4), nullable=True)
    forward_pe: Mapped[float | None] = mapped_column(Numeric(19, 4), nullable=True)
    earnings_growth: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    payout_ratio: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    dividend_rate: Mapped[float | None] = mapped_column(Numeric(19, 4), nullable=True)

    # Analist görüşü BAŞKASININ değerlendirmesi. "16 analistin ortalama hedefi
    # 95,39 TL" aktarılabilir bir olgudur; ürünün kendi görüşü olarak
    # aktarılması tavsiye olurdu ve prompt bunu ayrıca yasaklıyor.
    recommendation_key: Mapped[str | None] = mapped_column(String(24), nullable=True)
    analyst_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_mean_price: Mapped[float | None] = mapped_column(Numeric(19, 4), nullable=True)

    ex_dividend_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    earnings_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class IndexMembership(Base):
    """Bir enstrümanın hangi endekste yer aldığı.

    Ayrı bir tablo, çünkü üyelik ÇOKTAN ÇOĞA: AAPL hem Nasdaq-100'de hem de
    S&P 500'de. `investment_products.market` bunu taşıyamaz -- o alan hissenin
    işlem gördüğü BORSAYI söyler (AAPL için NASDAQ) ve bir hissenin tek bir
    borsası vardır. İkisini aynı sütuna sıkıştırmak, S&P sekmesinde Apple'ın,
    Microsoft'un ve Nvidia'nın görünmemesi demekti; endeksin en büyük
    üyelerini göstermeyen bir "S&P" sekmesi eksik değil, yanıltıcı olurdu.

    Üyelik listeleri lisanslı bir üründür; bu yüzden migration içinde elle ve
    tarihli yazılıyorlar (bkz. 0006, 0010, 0019).
    """

    __tablename__ = "index_memberships"
    __table_args__ = (
        UniqueConstraint("product_id", "index_code", name="uq_index_membership"),
        Index("idx_index_memberships_code", "index_code"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    product_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.investment_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: `BIST`, `SP500`, `NASDAQ100`. Ekranlardaki sekmelerin okuduğu değer.
    index_code: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class InvestmentAccount(Base):
    """A custody account. Minimal on purpose — enough to hang positions off."""

    __tablename__ = "investment_accounts"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    account_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    #: Aynı bankanın hesabı olduğu için IBAN'ı da var. Yokken hesap
    #: "para gönder" ekranında adreslenemiyor ve hareketleri hiçbir yerde
    #: görünmüyordu; kullanıcı için nakit tutan bir hesap, hareketi olmayan
    #: bir bakiyeden ibaret kalıyordu.
    iban: Mapped[Optional[str]] = mapped_column(String(34), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="TRY")
    cash_balance: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class CashMovement(Base):
    """Yatırım hesabının nakit defteri.

    Bakiyeyi üç ayrı yer yazıyordu -- alım/satım takası, bankacılık köprüsü ve
    yöneticinin para ekleme işlemi -- ve hiçbiri iz bırakmıyordu. Bakiyeden
    geriye doğru hesaplamak da mümkün değildi: yöneticinin eklediği para hiçbir
    kayıtta görünmediği için yeniden oynatma sessizce kayıyordu.

    Bu yüzden defter, bankacılıktaki `account_transactions` ile aynı biçimde
    tutuluyor: her satır kendi `balance_before`/`balance_after` değerini
    taşır, dolayısıyla hesabın belirli bir andaki durumu tüm geçmişi yeniden
    oynatmadan okunabilir.
    """

    __tablename__ = "cash_movements"
    __table_args__ = (
        Index("idx_cash_movements_account", "account_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    #: DEBIT = hesaptan çıktı, CREDIT = hesaba girdi. Bankacılık tarafıyla
    #: aynı sözlük; iki döküm yan yana okunabilsin.
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    balance_before: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    #: İşlemi doğuran kayıt: takasta öneri id'si, virmanda banka referansı.
    #: Yönetici düzeltmesinde None -- uydurmak yerine boş bırakılır.
    reference: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class PortfolioPosition(Base):
    """A holding. Follows the design in infra/intertech.sql:327.

    Only `quantity` and `average_buy_price` are synthetic; they are what an
    account would record and no price feed can supply them. Everything derived
    from them is computed against live prices at read time rather than stored,
    so a position can never show a market value that disagrees with the current
    quote.
    """

    __tablename__ = "portfolio_positions"
    __table_args__ = (
        UniqueConstraint("investment_account_id", "product_id", name="uq_portfolio_positions_holding"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    investment_account_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.investment_accounts.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.investment_products.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    average_buy_price: Mapped[float] = mapped_column(Numeric(19, 4), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class WatchlistItem(Base):
    """An instrument the user chose to follow.

    Replaces a "watchlist" that was not one: the endpoint used to return the
    first eight priced stocks per market in alphabetical order, so it showed
    the same list to everyone and reflected nobody's choice.

    `user_id` is a plain column rather than a foreign key into `auth.users`.
    Modules do not import each other's ORM classes (see the shared/ rule in
    CLAUDE.md); the database-level relationship still holds because both live
    in the same Postgres instance.
    """

    __tablename__ = "watchlist_items"
    __table_args__ = (
        # One row per user per instrument. Starring twice is idempotent
        # rather than an error, and the constraint is what makes it so.
        UniqueConstraint("user_id", "product_id", name="uq_watchlist_user_product"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.investment_products.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class AllocationTarget(Base):
    """Kullanıcının KENDİ belirlediği hedef ağırlık, kova başına bir satır.

    Sistemin önerdiği bir model portföy DEĞİL ve bilerek öyle değil.
    `compliance/rules.py:SUI-001`'in gerekçesi şunu söylüyor: "sistem ölçüm
    ile kullanıcının kendi beyanını karşılaştırır, bir ürünün kişiye
    uygunluğuna karar vermez." Hedefi sistemin koyması, tam olarak o kararı
    vermek olurdu -- üstelik dört SPK ürün grubundan yalnızca birinin
    (hisse) bu sistemde enstrümanı var, dolayısıyla önerilen hedefin çoğu
    uygulanamaz bir talimat olurdu.

    Kova ANAHTARLA saklanıyor, etiketle değil (`allocation.BUCKETS`): bir
    etiketi düzeltmek kimsenin kayıtlı hedefini geçersizleştirmemeli.

    `user_id` düz bir kolon, foreign key değil -- modüller birbirinin ORM
    sınıfını import etmiyor (bkz. CLAUDE.md shared/ kuralı).
    """

    __tablename__ = "allocation_targets"
    __table_args__ = (
        # Kova başına tek hedef. İkinci bir satır, hangisinin geçerli olduğunu
        # söyleyemeyen bir hedef bırakırdı.
        UniqueConstraint("user_id", "bucket", name="uq_allocation_target_bucket"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bucket: Mapped[str] = mapped_column(String(32), nullable=False)
    #: 0..100. Toplamın 100 olması router'da doğrulanıyor: burada saklamak
    #: satır başına bir kısıt, toplam ise satırlar ARASI bir kural.
    target_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
