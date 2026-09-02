"""Çeyreklik gelir tablosu — enstrüman başına dönem dönem bir satır.

`instrument_fundamentals` bir ANLIK GÖRÜNTÜ: alan başına tek güncel değer,
geçmiş yok, her turda üstüne yazılıyor. Bu yüzden "son çeyrek kârı önceki
çeyreğe göre şu kadar arttı" kurulamıyordu -- kıyaslanacak ikinci dönem hiç
saklanmıyordu. İki tablo AYRI, çünkü biri üstüne yazılıyor diğeri birikiyor.

ŞEMA ÖLÇÜLEREK TASARLANDI. Evrenden rastgele 40 BIST hissesi örneklendi:
34'ünde çeyreklik veri var, 6'sında hiç yok; dönem sayısı 5-7, ortalama 5,5.
Veri olanların 33'ünde hem son çeyrek, hem bir önceki, hem de bir yıl öncesi
dolu -- boşluklar serinin ESKİ ucunda toplanıyor.

DOĞAL ANAHTAR (product_id, period_end), sıra numarası değil. Sağlayıcının
dönemleri ardışık gelmiyor: AKBNK, GARAN ve EREGL'de 2025Q3 gelir tablosunda
hiç yok (nakit akışında var). "Son iki satırı al" diyen bir karşılaştırma o
üç hissede 2025Q2 ile 2025Q4'ü kıyaslar ve bunu söylemez.

DÖRT KALEM. Sağlayıcının gelir tablosu şirkete göre 33-52 satır; derin
örneklenen on iki sembolün HEPSİNDE bulunan yirmi kalemden yalnızca bunlar bu
kartın sorusunu cevaplıyor. `EBITDA` ve `EBIT` dışarıda: on iki sembolün
onunda var ve eksik olan ikisi banka -- banka muhasebesinde o kalem yok,
sıfır değil. `Basic EPS` de dışarıda ve bu ayrıca ölçüldü: 34 hissede son
çeyrekte 32 kez dolu, bir önceki çeyrekte YALNIZCA 3 kez. Seri olarak
saklamak neredeyse hep yarısı boş bir kolon açmak olurdu ve hisse başına kâr
zaten anlık tabloda duruyor.

Her sayısal kolon NULLABLE: 34 hissenin 16'sında serinin bir yerinde eksik
değer var ve sıfıra çevirmek "o çeyrek raporlandı, kâr sıfır çıktı" demek
olurdu.

Etiket ("2026Q2") saklanmıyor, `period_end`'den türetiliyor: hiçbir zaman
değişmeyecek ve tamamen ondan çıkarılabilen bir değer için ikinci bir sütun,
ikisinin ayrışabileceği bir yer açardı.

Geri alınabilir: tablo düşer, hiçbir mevcut satır etkilenmez.

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-02 16:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instrument_quarterly",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("total_revenue", sa.BigInteger(), nullable=True),
        sa.Column("net_income", sa.BigInteger(), nullable=True),
        sa.Column("pretax_income", sa.BigInteger(), nullable=True),
        sa.Column("operating_expense", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"], ["investment.investment_products.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id", "period_end", name="uq_instrument_quarterly_period"
        ),
        schema="investment",
    )
    op.create_index(
        "ix_investment_instrument_quarterly_product_id",
        "instrument_quarterly",
        ["product_id"],
        schema="investment",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_investment_instrument_quarterly_product_id",
        table_name="instrument_quarterly",
        schema="investment",
    )
    op.drop_table("instrument_quarterly", schema="investment")
