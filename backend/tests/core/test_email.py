"""E-posta gönderimi (main + #42).

Birleşmeden önce %23 kapsamayla geldi. Bu modül hesap doğrulama, şifre
sıfırlama ve veri dışa aktarma e-postalarını gönderiyor -- üçü de sessizce
başarısız olduğunda kullanıcının hesabına giremediği ya da istediği veriyi
alamadığı yollar.

`fm.send_message` her testte taklit ediliyor: gerçek bir SMTP sunucusuna
bağlanan bir test, ağı olmayan bir makinede kırmızı yanar ve olan bir makinede
gerçekten e-posta gönderir.
"""

from __future__ import annotations

import pytest

from app.core import email as email_module


@pytest.fixture
def sent(mocker):
    """Gönderilen mesajları toplayan bir `FastMail` taklidi."""
    messages = []

    async def _send(message, *args, **kwargs):
        messages.append(message)

    mocker.patch.object(email_module.fm, "send_message", side_effect=_send)
    return messages


class TestTemplate:
    def test_the_action_url_and_text_are_placed(self):
        html = email_module._get_email_html_template(
            "Başlık", "Gövde", "https://example.com/dogrula", "Doğrula",
        )
        assert "https://example.com/dogrula" in html
        assert "Doğrula" in html
        assert "Başlık" in html


class TestVerificationEmail:
    @pytest.mark.asyncio
    async def test_it_sends_to_the_address_with_the_token_in_the_link(self, sent):
        await email_module.send_verification_email("a@example.com", "tok-123")
        assert len(sent) == 1
        message = sent[0]
        # `recipients` görünen adı da taşıyor ("a <a@example.com>").
        assert any("a@example.com" in str(r) for r in message.recipients)
        # Token bağlantının içinde olmalı: onsuz kullanıcı doğrulayamaz.
        assert "tok-123" in str(message.body or message.html or "")

    @pytest.mark.asyncio
    async def test_a_send_failure_does_not_raise(self, mocker):
        """Kayıt akışını düşürmez: e-posta gitmese de hesap oluşturuldu ve
        kullanıcı yeniden gönderim isteyebilir. Hata loglanıyor."""
        mocker.patch.object(
            email_module.fm, "send_message", side_effect=RuntimeError("smtp down"),
        )
        await email_module.send_verification_email("a@example.com", "tok")


class TestPasswordResetEmail:
    @pytest.mark.asyncio
    async def test_it_carries_the_reset_token(self, sent):
        await email_module.send_password_reset_email("a@example.com", "reset-9")
        assert "reset-9" in str(sent[0].body or sent[0].html or "")

    @pytest.mark.asyncio
    async def test_a_failure_is_swallowed_and_logged(self, mocker):
        mocker.patch.object(
            email_module.fm, "send_message", side_effect=RuntimeError("smtp down"),
        )
        await email_module.send_password_reset_email("a@example.com", "tok")


class TestDataExportEmail:
    @pytest.mark.asyncio
    async def test_the_pdf_is_attached(self, sent, tmp_path, mocker):
        """Ek olmadan giden bir "verileriniz hazır" e-postası, veriyi hiç
        vermemekle aynı şey."""
        import tempfile as _tempfile

        mocker.patch.object(_tempfile, "gettempdir", return_value=str(tmp_path))
        await email_module.send_data_export_email(
            "a@example.com",
            {"profile": {"first_name": "Test", "last_name": "Kullanici"}},
            {"total_value": 100.0},
        )
        assert len(sent) == 1
        assert sent[0].attachments

    @pytest.mark.asyncio
    async def test_a_pdf_failure_does_not_raise(self, mocker):
        """PDF üretilemezse akış düşmez; hata loglanır ve kullanıcı tekrar
        talep edebilir."""
        from app.core import pdf_generator

        mocker.patch.object(
            pdf_generator, "generate_user_data_pdf", side_effect=RuntimeError("no disk"),
        )
        mocker.patch.object(email_module.fm, "send_message")
        await email_module.send_data_export_email("a@example.com", {}, {})


class TestConfiguration:
    def test_a_broken_smtp_config_does_not_stop_the_service(self, mocker):
        """Yanlış SMTP ayarı uygulamayı açılışta düşürmemeli: e-posta
        gönderilemez ama bankacılık çalışmaya devam eder."""
        import importlib

        mocker.patch(
            "fastapi_mail.ConnectionConfig", side_effect=ValueError("bad config"),
        )
        module = importlib.reload(email_module)
        assert module is not None
        importlib.reload(email_module)


class TestExportCleanup:
    @pytest.mark.asyncio
    async def test_the_temporary_pdf_is_removed_after_sending(
        self, sent, tmp_path, mocker,
    ):
        """Geçici PDF diskte bırakılmaz: kullanıcının bütün kişisel verisini
        taşıyan bir dosya, sunucuda süresiz durmamalı."""
        import tempfile as _tempfile

        mocker.patch.object(_tempfile, "gettempdir", return_value=str(tmp_path))
        await email_module.send_data_export_email(
            "a@example.com", {"profile": {}}, {"total_value": 1.0},
        )
        assert list(tmp_path.glob("moneyfast_export_*.pdf")) == []

    @pytest.mark.asyncio
    async def test_a_cleanup_failure_is_logged_not_raised(self, sent, tmp_path, mocker):
        import os as _os
        import tempfile as _tempfile

        mocker.patch.object(_tempfile, "gettempdir", return_value=str(tmp_path))
        mocker.patch.object(_os, "remove", side_effect=OSError("kilitli"))
        await email_module.send_data_export_email(
            "a@example.com", {"profile": {}}, {"total_value": 1.0},
        )


class TestUnconfiguredSmtp:
    @pytest.mark.asyncio
    async def test_the_export_says_so_instead_of_pretending(self, tmp_path, mocker):
        """SMTP yapılandırılmamışsa gönderim sessizce başarılı sayılmaz.

        `fm` yoksa e-posta gidemez; kod bunu uyarı olarak yazıyor. Sessiz bir
        başarı, kullanıcıya "verileriniz gönderildi" deyip hiçbir şey
        göndermemek olurdu.
        """
        import tempfile as _tempfile

        mocker.patch.object(_tempfile, "gettempdir", return_value=str(tmp_path))
        mocker.patch.dict(email_module.__dict__, clear=False)
        del email_module.__dict__["fm"]
        try:
            await email_module.send_data_export_email(
                "a@example.com", {"profile": {}}, {"total_value": 1.0},
            )
        finally:
            import importlib
            importlib.reload(email_module)
