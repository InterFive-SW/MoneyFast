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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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


class DirectionSignal(Base):
    """Bir enstrümanın bir vadedeki yön okuması, gecelik hesaplanmış hâliyle.

    Neden saklanıyor: Piyasalar ekranı "ölçülen kanıt yönü" kolonuyla
    sıralanabiliyor ve 1.011 enstrümanın okumasını istek anında hesaplamak
    sembol başına üç sorgu demek. Tek sembol sorulduğunda hâlâ TAZE
    hesaplanıyor (`GET /market/direction`); burası yalnızca tarama için.

    `computed_at` gizlenmiyor: bayat bir hesap "şu tarih itibarıyla" diye
    sunuluyor. Bir okumanın ne zaman yapıldığını söylemeden göstermek, dünkü
    ölçümü bugünün ölçümü gibi göstermek olurdu.

    `evidence` JSONB olarak saklanıyor çünkü tarama satırı da gerekçesini
    taşımak zorunda -- gerekçesiz bir yön, kullanıcının doğrulayamayacağı bir
    iddiadır. Sorgulanmıyor, yalnızca okunuyor; ayrı bir tabloya bölmek
    okumayı bir birleştirmeye çevirirdi.
    """

    __tablename__ = "direction_signals"
    __table_args__ = (
        Index("idx_direction_signals_horizon_lean", "horizon", "lean"),
        {"schema": SCHEMA},
    )

    product_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    horizon: Mapped[str] = mapped_column(String(4), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    #: UP_LEAN / DOWN_LEAN / MIXED / INSUFFICIENT
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Ölçülemeyen bir okumada None -- sıfır değil, çünkü sıfır "ölçtük ve
    #: dengede" demek olurdu ve tarama onu MIXED satırlarla karıştırırdı.
    lean: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    observations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class NewsImpact(Base):
    """Bir haberin bir enstrümana etkisi hakkında YAPILANDIRILMIŞ yargı.

    Neden düzyazı değil de satır: bu yargıyı LLM üretiyor ve bir modelin
    ürettiği metin denetlenemez. Satır olarak saklandığında her iddia belirli
    bir habere kadar izlenebiliyor, günlük özet KODDA toplanabiliyor, ve
    toplayıcı test edilebiliyor. Model yorumluyor, kod topluyor ve cümleyi
    kuruyor -- `widgets.py` ve `sources.py` ile aynı ayrım.

    `mechanism` bir CÜMLE, sayı değil. Sayılar ölçümden gelir; modelin
    ürettiği bir yüzde, ölçülmemiş bir şeyi ölçülmüş gibi gösterirdi.

    `scope` yayılmayı doğrudan etkiden ayırıyor: bir savunma ihalesi haberi
    ASELS için DIRECT, tedarikçisi için SPILLOVER. İkisini aynı listede
    karıştırmak, haberin kimin hakkında olduğunu okunamaz yapardı.

    `confidence` modelin kendi beyanı ve öyle olduğu biliniyor: bir ölçüm
    değil. Sıralamada kullanılıyor, kullanıcıya sayı olarak GÖSTERİLMİYOR.
    """

    __tablename__ = "news_impacts"
    __table_args__ = (
        # Aynı haber aynı enstrüman için iki kez yargılanmaz.
        Index("uq_news_impacts_news_symbol", "news_id", "symbol", unique=True),
        # Günlük özet: "şu tarihten beri şu sembolleri etkileyen haberler".
        Index("idx_news_impacts_symbol_time", "symbol", "published_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    news_id: Mapped[str] = mapped_column(String, nullable=False)
    #: Enstrüman kodu. Evren dışı bir ad KAYDEDİLMEZ -- model uydurabiliyor
    #: ve olmayan bir sembol için etki saklamak, ekranda bulunamayan bir
    #: satır demek.
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    #: UP / DOWN / NEUTRAL. NEUTRAL "etkisiz" demek, "ölçemedim" değil --
    #: ölçülemeyen haber hiç satır üretmiyor.
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    #: DIRECT / SPILLOVER
    scope: Mapped[str] = mapped_column(String(12), nullable=False, default="DIRECT")
    #: LOW / MEDIUM / HIGH. Modelin beyanı; ölçüm değil.
    magnitude: Mapped[str] = mapped_column(String(8), nullable=False, default="LOW")
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0.5)
    #: NEDEN. Tek Türkçe cümle, kullanıcıya gösterilecek hâliyle.
    mechanism: Mapped[str] = mapped_column(Text, nullable=False)
    #: Haberin yayın zamanı, `news_items`tan kopyalanıyor: günlük özet
    #: sorgusu bir birleştirme olmadan tarihe göre süzebilsin.
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Hangi model üretti. Yargıyı üretenin değiştiğini bilmeden, dünkü
    #: yargıyla bugünkünü karşılaştırmak yanıltırdı.
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
