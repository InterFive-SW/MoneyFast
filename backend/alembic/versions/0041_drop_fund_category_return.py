"""market.funds.category_return kalkıyor + uydurulmuş şemsiye değerleri siliniyor

Revision ID: 0041
Revises: 0040

İki düzeltme, tek sebep: `fonProfilDtyGetir` sanıldığı şeyi döndürmüyor.

O uç fonun profilini değil, KARŞILAŞTIRMA GRAFİĞİNİN gösterge listesini
döndürüyor -- ALTIN, BIST100, BIST30 ... -- ve yanıt HER FON İÇİN AYNI.
Toplayıcı ilk satırın `fonTuru` alanını şemsiye türü, `fonTurGetiri` alanını
da kategori getirisi sanıyordu.

Ölçülen sonuç: 1.054 aktif fonun 1.021'i "ALTIN" şemsiyesine yazıldı ve
hepsine aynı getiri (%46,6) kategori ortalaması diye kondu. Boş bir sütundan
kötü: uydurulmuş bir değer doğruymuş gibi süzülüyor ve ekranda bir ölçüm
gibi duruyor.

* `category_return` SÜTUNU DÜŞÜYOR. Doğru kaynağı yok: gösterge listesi
  fonun kategorisiyle eşleşmiyor ve TEFAS'ın döndürdüğü hiçbir alan
  "kategorinin ortalama getirisi" değil. Bir gün dolacakmış gibi duran boş
  bir sütun bırakmak, aynı sözü ikinci kez vermek olurdu. Fonun kategori
  içindeki SIRASI (`category_rank`/`category_size`) gerçek ve kalıyor --
  "1.333 fon içinde 751." zaten aynı soruyu cevaplıyor.
* Uydurulmuş şemsiye değerleri NULL'lanıyor. Doğru kaynak `fonTurGetir` +
  `sfonTurKod` ile süzülmüş günlük anlık görüntü; toplayıcı eksik
  (`NULL`) olanları yeniden dolduruyor, dolayısıyla temizlemek yeniden
  çekilmelerini sağlıyor.
"""

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

SCHEMA = "market"

#: Gösterge listesinin ilk satırı. Gerçek şemsiye adlarının hepsi
#: "... Şemsiye Fonu" ile bitiyor, dolayısıyla bu değer yalnızca hatalı
#: yoldan gelmiş olabilir.
FABRICATED_UMBRELLA = "ALTIN"


def upgrade() -> None:
    op.execute(
        sa.text(
            f"UPDATE {SCHEMA}.funds SET umbrella = NULL WHERE umbrella = :bad"
        ).bindparams(bad=FABRICATED_UMBRELLA)
    )
    op.drop_column("funds", "category_return", schema=SCHEMA)


def downgrade() -> None:
    op.add_column(
        "funds",
        sa.Column("category_return", sa.Numeric(12, 4), nullable=True),
        schema=SCHEMA,
    )
    # Silinen şemsiye değerleri geri getirilmiyor: uydurulmuşlardı ve
    # toplayıcı doğrusunu zaten yeniden yazıyor.
