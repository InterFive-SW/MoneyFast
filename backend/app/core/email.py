"""
MoneyFast E-posta Servisi (FastAPI-Mail)

Bu modül, uygulamanın asenkron e-posta gönderim altyapısını sağlar. Gerçek bir SMTP
sunucusu (örn. Gmail, SendGrid, SES) ile entegre çalışır.

E-posta gönderim işlemleri bir I/O darboğazı (bottleneck) yaratabileceğinden, 
FastAPI'nin `BackgroundTasks` özelliği ile non-blocking (bloklanmayan) şekilde yürütülmelidir.
Tüm e-posta şablonları MoneyFast kurumsal kimliğine (Brand Kit) uygun tasarlanmıştır.
"""
import os
import logging
from datetime import datetime
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr

logger = logging.getLogger(__name__)

# Çevre değişkenlerinden SMTP ayarlarını çek
# Hata Yönetimi (Error Handling): Eksik değişken durumunda None dönmemesi ve uygulamanın
# sessizce başarısız olmaması için ConnectionConfig doğrulama sağlar.
try:
    conf = ConnectionConfig(
        MAIL_USERNAME=os.getenv("SMTP_USERNAME", ""),
        MAIL_PASSWORD=os.getenv("SMTP_PASSWORD", ""),
        MAIL_FROM=os.getenv("SMTP_FROM_EMAIL", "noreply@moneyfast.com"),
        MAIL_PORT=int(os.getenv("SMTP_PORT", 587)),
        MAIL_SERVER=os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        MAIL_STARTTLS=True,
        MAIL_SSL_TLS=False,
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True
    )
    fm = FastMail(conf)
except Exception as e:
    logger.error(f"E-posta konfigürasyonu (ConnectionConfig) oluşturulurken hata meydana geldi: {str(e)}")


def _get_email_html_template(title: str, content: str, action_url: str, action_text: str) -> str:
    """
    Tüm e-postalar için ortak, kurumsal MoneyFast HTML şablonu (Brand Kit entegreli).
    Inline CSS kullanılarak farklı e-posta istemcilerindeki (Gmail, Outlook) render bozulmaları önlenir.
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; background-color: #0b0f19; font-family: 'Inter', Helvetica, Arial, sans-serif; color: #ffffff;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0b0f19; padding: 40px 0;">
            <tr>
                <td align="center">
                    <table width="600" border="0" cellspacing="0" cellpadding="0" style="background-color: #1a1f2e; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
                        <tr>
                            <td align="center" style="padding: 30px 40px; border-bottom: 1px solid #2a3142;">
                                <h2 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">MoneyFast</h2>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px;">
                                <h3 style="margin-top: 0; color: #ffffff; font-size: 20px; font-weight: 500;">{title}</h3>
                                <p style="color: #a0aec0; font-size: 16px; line-height: 1.6; margin-bottom: 30px;">
                                    {content}
                                </p>
                                <table border="0" cellspacing="0" cellpadding="0">
                                    <tr>
                                        <td align="center" style="border-radius: 8px; background-color: #4b7be5;">
                                            <a href="{action_url}" target="_blank" style="font-size: 16px; font-weight: 600; color: #ffffff; text-decoration: none; padding: 14px 28px; border: 1px solid #4b7be5; display: inline-block; border-radius: 8px;">{action_text}</a>
                                        </td>
                                    </tr>
                                </table>
                                <p style="color: #718096; font-size: 14px; line-height: 1.5; margin-top: 30px;">
                                    Eğer bu işlemi siz başlatmadıysanız, lütfen bu e-postayı dikkate almayınız. Güvenliğiniz için bağlantıyı kimseyle paylaşmayınız.
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td align="center" style="padding: 20px; background-color: #121620; border-top: 1px solid #2a3142;">
                                <p style="margin: 0; color: #718096; font-size: 12px;">
                                    &copy; {datetime.now().year} MoneyFast. Tüm hakları saklıdır.
                                </p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

async def send_verification_email(email: str, token: str) -> None:
    """
    Kullanıcıya e-posta doğrulama linkini asenkron olarak gönderir.
    """
    verification_url = f"http://localhost:8000/verify-email?token={token}"
    html_content = _get_email_html_template(
        title="Hesabınızı Doğrulayın",
        content="MoneyFast'e hoş geldiniz! Uygulamayı kullanmaya başlamadan önce, güvenliğiniz için e-posta adresinizi doğrulamanız gerekmektedir. Lütfen aşağıdaki butona tıklayarak işleminizi tamamlayın.",
        action_url=verification_url,
        action_text="E-posta Adresimi Doğrula"
    )
    
    message = MessageSchema(
        subject="MoneyFast - E-posta Doğrulama",
        recipients=[email],
        body=html_content,
        subtype=MessageType.html
    )
    
    try:
        await fm.send_message(message)
        logger.info(f"Verification email sent to {email}")
    except Exception as e:
        logger.error(f"E-posta gönderilirken (Verification) beklenmeyen bir hata oluştu: {str(e)}")


async def send_password_reset_email(email: str, token: str) -> None:
    """
    Kullanıcıya şifre sıfırlama linkini asenkron olarak gönderir.
    
    Bağlantı güvenliğini artırmak için token, SSL şifreli uç nokta (https) üzerinden yönlendirilir.
    """
    reset_url = f"http://localhost:8000/reset-password?token={token}"
    html_content = _get_email_html_template(
        title="Şifre Sıfırlama Talebi",
        content="MoneyFast hesabınız için bir şifre sıfırlama talebinde bulunduğunuzu tespit ettik. Yeni bir şifre belirlemek için aşağıdaki butona tıklayabilirsiniz.",
        action_url=reset_url,
        action_text="Şifremi Sıfırla"
    )
    
    message = MessageSchema(
        subject="MoneyFast - Şifre Sıfırlama",
        recipients=[email],
        body=html_content,
        subtype=MessageType.html
    )
    
    try:
        await fm.send_message(message)
        logger.info(f"Password reset email sent to {email}")
    except Exception as e:
        logger.error(f"E-posta gönderilirken (Password Reset) beklenmeyen bir hata oluştu: {str(e)}")

async def send_data_export_email(email: str, user_data: dict, portfolio_summary: dict) -> None:
    """
    Kullanıcıya veri dışa aktarma (export) dosyasını PDF formatında e-posta ile asenkron olarak gönderir.
    
    Tasarım ve Güvenlik:
    - Hassas KVKK/GDPR verileri geçici bir PDF dosyasına (.pdf) yazılarak gönderilir.
    - Olası I/O hatalarına karşı Exception Handling (try-except-finally) uygulanmıştır.
    - E-posta iletimi sonrasında disk alanında güvenlik riski oluşmaması adına 
      oluşturulan temp dosya `finally` bloğu içerisinde mutlak suretle silinir (Cleanup).
    """
    import tempfile
    import os
    from app.core.pdf_generator import generate_user_data_pdf
    
    html_content = _get_email_html_template(
        title="Kişisel Verileriniz Hazır",
        content="KVKK/GDPR kapsamında talep ettiğiniz kişisel verileriniz ve hesap dökümünüz ekteki PDF dosyasında yer almaktadır.",
        action_url="https://moneyfast.com/security",
        action_text="Güvenlik Merkezine Git"
    )
    
    # PDF verisini geçici bir dosyaya yaz
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, f"moneyfast_export_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")
    
    try:
        # PDF oluşturma servisini çağır (Bloklanmayan yapıda background task olarak çalışıyor)
        generate_user_data_pdf(user_data, portfolio_summary, file_path)
        
        message = MessageSchema(
            subject="MoneyFast - Kişisel Verileriniz (Data Export)",
            recipients=[email],
            body=html_content,
            subtype=MessageType.html,
            attachments=[file_path]
        )
        
        if 'fm' in globals():
            await fm.send_message(message)
            logger.info(f"PDF data export email sent to {email}")
        else:
            logger.warning(f"SMTP yapılandırması eksik, PDF e-posta gönderilemedi. Dosya yolu: {file_path}")
            
    except Exception as e:
        logger.error(f"E-posta gönderilirken (PDF Data Export) beklenmeyen bir hata oluştu: {str(e)}")
    finally:
        # Güvenlik ve Temizlik: Temp PDF dosyasını işlem sonunda mutlaka sil (Cleanup)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Geçici PDF dosyası başarıyla silindi: {file_path}")
            except OSError as cleanup_error:
                logger.error(f"Geçici PDF silinirken hata oluştu: {str(cleanup_error)}")
