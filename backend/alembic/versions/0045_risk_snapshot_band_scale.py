"""Bir anlık görüntünün etiketi hangi ölçekte yazıldı.

Ölçülen risk bantları üçten dörde çıkıyor (`profile.BANDS`): eski "Düşük"
bandının üst kısmı artık "Risksiz". Tarihsel satırlar **geriye dönük yeniden
hesaplanmıyor** -- o gün ölçülen buydu, ve bir kaydı sonradan başka bir
ölçeğe göre yeniden yazmak, kaydın kendisini geçersiz kılar.

Dolayısıyla seride iki ölçek yan yana duruyor. Ölçeği satırla birlikte
saklamadan bunu ayırt etmenin yolu yok: üç bantlı bir "Düşük" ile dört bantlı
bir "Düşük" aynı etiket ama farklı iki iddia, çünkü ikincisinin altında bir
bant daha var. `questionnaire_version` ile aynı gerekçe.

Geriye doldurma `"v1"` ile yapılıyor, NULL ile değil: mevcut her satır bu
migration'dan önce yazıldı, yani hepsi üç bantlı ölçekte. "Bilinmiyor" demek,
bilinen bir şeyi bilinmiyor diye kaydetmek olurdu.

Revision ID: 0045
Revises: 0044
"""

from alembic import op
import sqlalchemy as sa

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

#: Bu migration'dan önce yazılmış her satırın ölçeği.
LEGACY_SCALE = "v1"

#: Bundan sonra yazılacakların ölçeği (`profile.BAND_SCALE`). Sabit burada
#: TEKRAR yazılı ve bilerek: migration'lar uygulama kodunu import etmiyor,
#: çünkü bir migration geçmişte donmuş bir adım ve altından değişen bir
#: sabite bağlanması onu geriye dönük olarak başka bir şeye çevirirdi.
CURRENT_SCALE = "v2"


def upgrade() -> None:
    op.add_column(
        "risk_snapshots",
        sa.Column("band_scale", sa.String(length=16), nullable=True),
        schema="risk",
    )
    op.execute(
        f"UPDATE risk.risk_snapshots SET band_scale = '{LEGACY_SCALE}' "
        "WHERE band_scale IS NULL"
    )
    op.alter_column(
        "risk_snapshots",
        "band_scale",
        nullable=False,
        server_default=CURRENT_SCALE,
        schema="risk",
    )


def downgrade() -> None:
    op.drop_column("risk_snapshots", "band_scale", schema="risk")
