"""Market news storage.

News lands in two places, on purpose. Rows here serve the dashboard feed —
"latest twenty, newest first" is a cheap indexed query. The same articles are
also chunked and embedded into `vector-db` by the ingestor so the chatbot can
retrieve and cite them; that is a semantic-similarity access pattern and a
completely different query.

Storing it once and serving both from either side would mean the dashboard
paying an embedding search to list headlines, or the retriever having no
corpus. See docs/VECTOR_DB_ARCHITECTURE.md, "Corpus boundary".
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SCHEMA = "market"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (
        Index("idx_news_items_published", "published_at"),
        # `related_symbols` üzerinde `overlap` (`&&`) çalışan iki sorgu var --
        # portföye dokunan haberler ve hisse detayının haber listesi. Dizi
        # çakışması B-tree ile hızlanmaz; GIN olmadan ikisi de tam tarama.
        Index(
            "idx_news_items_related_symbols",
            "related_symbols",
            postgresql_using="gin",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    #: SHA-256 of the article text. The deduplication key: re-running a feed
    #: must be a no-op, not a second copy of every headline.
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="tr")
    #: Haberin dokunduğu enstrümanlar. Kaynak etiketliyorsa (KAP bildirimleri
    #: `stockCode` taşıyor) o kullanılır; RSS beslemeleri etiketlemediği için
    #: `symbol_match` başlık ve özetten çözer -- tam kelime, kesin ad, bulanık
    #: eşleşme YOK. Kural değişmedi, yalnızca nereye taşındı: yanlış bir
    #: etiket, başka bir şirketin haberini bu hissenin sayfasına koyar.
    related_symbols: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Fund(Base):
    """Bir TEFAS fonu — bugünkü hâli.

    Sütunlar TEFAS'ın gerçekten döndürdüğü kadar. Arayüzün mock'ta okuduğu
    yönetim ücreti, stopaj, risk değeri ve hisse bazında dağılım API'de YOK
    (HAR kaydındaki 85 alanın hepsi tarandı) ve o alanlar için sütun
    açılmadı: boş bir sütun, bir gün dolacakmış gibi duran bir söz olurdu.
    """

    __tablename__ = "funds"
    __table_args__ = (
        Index("idx_funds_founder", "founder"),
        Index("idx_funds_umbrella", "umbrella"),
        Index("idx_funds_type", "fund_type"),
        {"schema": SCHEMA},
    )

    #: TEFAS'ın kendi kimliği. Ayrı bir yüzey id'si üretmek, iki kimlik
    #: arasında eşleme tutmak demek olurdu.
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    founder: Mapped[str | None] = mapped_column(String(200), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(200), nullable=True)
    umbrella: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fund_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(19, 6), nullable=True)
    shares: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    investors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size: Mapped[float | None] = mapped_column(Numeric(24, 2), nullable=True)
    #: Fon fiyatı GÜNLÜKTÜR. Zaman damgası taşımak, olmayan bir anlık değeri
    #: varmış gibi gösterirdi.
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: TEFAS'ın kendi kategori ölçümleri -- hesaplanmış değil, ölçülmüş.
    #: "86 para piyasası fonu içinde 71." Bir getirinin iyi mi kötü mü
    #: olduğunu tek başına getiri söylemiyor; sıra söylüyor.
    category_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Kategorinin ortalama getirisi. %38'in iyi olup olmadığı ancak
    #: kategori %41 yaptıysa cevaplanabiliyor.
    category_return: Mapped[float | None] = mapped_column(Numeric(12, 4), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class FundPrice(Base):
    """Bir fonun bir günkü NAV'ı.

    `funds`tan ayrı, çünkü ayrı bir erişim deseni: orası "bugün ne durumda"
    sorusuna tek satırla cevap veriyor, burası bir seri ve yalnızca grafik
    okuyor. `market_quotes` / `market_candles` ayrımının aynısı.
    """

    __tablename__ = "fund_prices"
    __table_args__ = (
        Index("idx_fund_prices_code_time", "code", "as_of"),
        {"schema": SCHEMA},
    )

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
    price: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False)
