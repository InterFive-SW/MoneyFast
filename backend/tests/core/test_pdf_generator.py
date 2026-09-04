"""Kullanıcı veri dışa aktarma PDF'i.

#42 ile geldi ve hiç testi yoktu (75 satır, %0 kapsama). Bu dosya bir
kullanıcının bütün kişisel verisini üretip e-postayla gönderiyor; sessizce
bozulması, birinin talep ettiği veriyi hiç alamaması ya da eksik alması
demek.
"""

from __future__ import annotations

import os

import pytest

from app.core import pdf_generator


PROFILE = {
    "first_name": "Test",
    "last_name": "Kullanici",
    "tc_no": "12345678901",
    "email": "test@dummy.moneyfast.local",
    "phone_number": "+905550000000",
    "created_at": "2026-01-15",
}
SUMMARY = {"total_value": 1_382_868.11, "cash": 165_577.30, "bist": 388_549.75, "us": 20_616.18}


class TestGenerateUserDataPdf:
    def test_it_writes_a_real_pdf(self, tmp_path):
        out = tmp_path / "export.pdf"
        pdf_generator.generate_user_data_pdf({"profile": PROFILE}, SUMMARY, str(out))

        assert out.exists()
        # Gerçekten bir PDF: sihirli bayt dizisi. Boş ya da yarım bir dosya
        # kullanıcıya "verileriniz hazır" deyip boş bir ek göndermek olurdu.
        assert out.read_bytes().startswith(b"%PDF")
        assert out.stat().st_size > 800

    def test_the_numbers_reach_the_document(self, tmp_path, mocker):
        """Tutarlar belgeye YAZILIYOR.

        Bayt dizisinde aranmıyor: fpdf çıktıyı sıkıştırıyor, dolayısıyla
        metnin ham dosyada görünmemesi bir şey kanıtlamaz. Yazma çağrıları
        dinleniyor -- test edilen şey belgeye ne verildiği.
        """
        written = []
        original = pdf_generator.MoneyFastPDF.cell

        def spy(self, *args, **kwargs):
            for arg in args:
                if isinstance(arg, str):
                    written.append(arg)
            return original(self, *args, **kwargs)

        mocker.patch.object(pdf_generator.MoneyFastPDF, "cell", spy)
        pdf_generator.generate_user_data_pdf(
            {"profile": PROFILE}, SUMMARY, str(tmp_path / "export.pdf"),
        )
        joined = " ".join(written)
        assert "1,382,868.11" in joined
        assert "Test Kullanici" in joined
        assert "12345678901" in joined

    def test_missing_fields_render_as_a_dash_not_a_crash(self, tmp_path):
        """Eksik bir alan belgenin tamamını düşürmemeli: dışa aktarma,
        elde ne varsa onu vermek için var."""
        out = tmp_path / "sparse.pdf"
        pdf_generator.generate_user_data_pdf({"profile": {}}, {}, str(out))
        assert out.read_bytes().startswith(b"%PDF")

    def test_no_profile_key_at_all_is_tolerated(self, tmp_path):
        out = tmp_path / "empty.pdf"
        pdf_generator.generate_user_data_pdf({}, {}, str(out))
        assert out.exists()

    def test_an_unwritable_path_is_raised_not_swallowed(self, tmp_path):
        """Yazılamayan bir yol sessizce yutulursa, çağıran "PDF hazır" sanıp
        olmayan bir dosyayı eklemeye çalışır."""
        with pytest.raises(Exception):
            pdf_generator.generate_user_data_pdf(
                {"profile": PROFILE}, SUMMARY, str(tmp_path / "yok" / "olmayan.pdf"),
            )

    def test_the_logo_is_drawn_when_it_exists(self, tmp_path, mocker):
        """Logo yoksa başlık yine basılıyor; varsa çiziliyor. İki dal da
        gerçek: geliştirici makinesinde dosya yok, konteynerde var."""
        mocker.patch.object(pdf_generator.os.path, "exists", return_value=True)
        image = mocker.patch.object(pdf_generator.MoneyFastPDF, "image")
        out = tmp_path / "logo.pdf"
        pdf_generator.generate_user_data_pdf({"profile": PROFILE}, SUMMARY, str(out))
        assert image.called

    def test_it_works_without_the_logo(self, tmp_path, mocker):
        mocker.patch.object(pdf_generator.os.path, "exists", return_value=False)
        out = tmp_path / "nologo.pdf"
        pdf_generator.generate_user_data_pdf({"profile": PROFILE}, SUMMARY, str(out))
        assert out.read_bytes().startswith(b"%PDF")
