"""ABD hisse kovasının ölçülebilir vekili.

Dengeleme ekranı her şablonun ÖLÇÜLEN geçmiş oynaklığını gösteriyor ve o
ölçüm kova başına bir fiyat serisi istiyor. Evrende BIST için `XU100`, altın
için `XAUUSD`, döviz için `USDTRY` vardı; ABD hisse kovasının karşılığı
YOKTU. `INDEX_CODES = {"SP500", "NASDAQ100"}` yalnızca ÜYELİK tablosu --
hangi hissenin hangi endekste olduğunu söylüyor, endeksin kendi serisini
değil.

Vekilsiz bir kova iki kötü seçenekten birini dayatırdı: kovayı ölçümün
dışında bırakıp ağırlığını sessizce yok saymak, ya da onu BIST'in oynaklığıyla
doldurmak. İkincisi ölçmediğimiz bir şeyi ölçmüş gibi göstermek olurdu.

Migration atıldığı an SPX'in HİÇ BARI YOKTUR: `candle-topup` çalışana kadar
`us_equity` ölçülemez ve şablon "ABD Hisse kovası için yeterli fiyat geçmişi
yok" der. O yol savunma amaçlı bir dal değil, gerçekten geçilen bir yol.

Revision ID: 0043
Revises: 0042
"""

from alembic import op
import sqlalchemy as sa

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

#: `0005`'teki kalıbın aynısı: (sembol, sağlayıcı kodu, ad, tür, piyasa, kur).
#: `^GSPC` sağlayıcının S&P 500 endeks serisi; dolar cinsinden ve TL'ye
#: çevrilerek ölçülüyor -- çevirmemek, ABD kovasını TL yatırımcısı için
#: sistematik olarak sakin gösterirdi.
PRODUCTS = [
    ("SPX", "^GSPC", "S&P 500 Endeksi", "index", "NASDAQ", "USD"),
]


def upgrade() -> None:
    connection = op.get_bind()
    for symbol, data_symbol, name, product_type, market, currency in PRODUCTS:
        connection.execute(
            sa.text(
                """
                INSERT INTO investment.investment_products
                    (id, symbol, data_symbol, name, product_type, market,
                     currency_code, status, created_at, updated_at)
                VALUES
                    (gen_random_uuid()::text, :symbol, :data_symbol, :name,
                     :product_type, :market, :currency, 'active', now(), now())
                ON CONFLICT (symbol) DO UPDATE
                    SET data_symbol = EXCLUDED.data_symbol,
                        name = EXCLUDED.name,
                        updated_at = now()
                """
            ),
            {
                "symbol": symbol,
                "data_symbol": data_symbol,
                "name": name,
                "product_type": product_type,
                "market": market,
                "currency": currency,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM investment.investment_products WHERE symbol = ANY(:symbols)"
        ),
        {"symbols": [row[0] for row in PRODUCTS]},
    )
