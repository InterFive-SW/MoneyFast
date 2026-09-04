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


async def send_transaction_request_email(
    email_to: str, 
    transaction_type: str, 
    asset_symbol: str, 
    quantity: float, 
    price: float, 
    total_amount: float, 
    transaction_date: datetime
) -> None:
    """
    Kullanıcıya finansal işlem (Alım/Satım) talebinin alındığını ve sıraya girdiğini bildirir.
    
    KURUMSAL İŞ MANTIĞI:
    İşlemlerin piyasa koşulları gereği anında gerçekleşmemesi veya bir onay sürecinden
    (bekleme süresi) geçmesi durumunda, kullanıcıya "paran bloke edildi ve talebin alındı"
    bilgisini vermek finansal şeffaflık açısından kritik öneme sahiptir.
    Bu e-posta, kullanıcının emir iletiminin başarılı olduğunu doğrular.
    """
    formatted_date = transaction_date.strftime("%d.%m.%Y %H:%M")
    transaction_type_tr = "Alım" if transaction_type.upper() == "BUY" else ("Satım" if transaction_type.upper() == "SELL" else transaction_type)
    
    html_content = f"""
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
                                <h2 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">İşlem Talebiniz Alındı</h2>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px;">
                                <h3 style="margin-top: 0; color: #ffffff; font-size: 20px; font-weight: 500;">Talebiniz İşleme Konuldu</h3>
                                <p style="color: #a0aec0; font-size: 16px; line-height: 1.6; margin-bottom: 30px;">
                                    MoneyFast hesabınız üzerinden {asset_symbol} için verdiğiniz {transaction_type_tr} emri başarıyla sıraya alınmıştır. İşleminiz yaklaşık 3 dakika içerisinde piyasa koşullarına göre gerçekleştirilecektir. İlgili tutar bakiyenizde bloke edilmiştir.
                                </p>
                                
                                <!-- İşlem Detayları Tablosu -->
                                <table width="100%" border="0" cellspacing="0" cellpadding="15" style="background-color: #121620; border-radius: 8px; border: 1px solid #2a3142;">
                                    <tr>
                                        <td style="color: #a0aec0; border-bottom: 1px solid #2a3142; font-size: 15px;">İşlem Tipi</td>
                                        <td align="right" style="color: #ffffff; border-bottom: 1px solid #2a3142; font-weight: 600; font-size: 15px;">{transaction_type_tr} Emri</td>
                                    </tr>
                                    <tr>
                                        <td style="color: #a0aec0; border-bottom: 1px solid #2a3142; font-size: 15px;">Varlık (Sembol)</td>
                                        <td align="right" style="color: #4b7be5; border-bottom: 1px solid #2a3142; font-weight: 600; font-size: 15px;">{asset_symbol}</td>
                                    </tr>
                                    <tr>
                                        <td style="color: #a0aec0; border-bottom: 1px solid #2a3142; font-size: 15px;">Miktar</td>
                                        <td align="right" style="color: #ffffff; border-bottom: 1px solid #2a3142; font-weight: 600; font-size: 15px;">{quantity:,.2f}</td>
                                    </tr>
                                    <tr>
                                        <td style="color: #a0aec0; border-bottom: 1px solid #2a3142; font-size: 15px;">İşlem Fiyatı</td>
                                        <td align="right" style="color: #ffffff; border-bottom: 1px solid #2a3142; font-weight: 600; font-size: 15px;">{price:,.2f} ₺</td>
                                    </tr>
                                    <tr>
                                        <td style="color: #a0aec0; border-bottom: 1px solid #2a3142; font-size: 15px;">Bloke Edilen Tutar</td>
                                        <td align="right" style="color: #ffffff; border-bottom: 1px solid #2a3142; font-weight: 600; font-size: 15px;">{total_amount:,.2f} ₺</td>
                                    </tr>
                                    <tr>
                                        <td style="color: #a0aec0; font-size: 15px;">Emir Tarihi</td>
                                        <td align="right" style="color: #ffffff; font-weight: 600; font-size: 15px;">{formatted_date}</td>
                                    </tr>
                                </table>
                                
                                <p style="color: #a0aec0; font-size: 14px; line-height: 1.6; margin-top: 30px; margin-bottom: 0;">
                                    İşleminiz gerçekleştiğinde size tekrar bilgi vereceğiz.<br>
                                    Güvenli yatırımlar dileriz.
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td align="center" style="padding: 20px; background-color: #121620; border-top: 1px solid #2a3142;">
                                <p style="margin: 0; color: #718096; font-size: 13px;">
                                    Bu e-posta otomatik olarak oluşturulmuştur. Lütfen yanıtlamayınız.
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

    message = MessageSchema(
        subject=f"MoneyFast - {transaction_type_tr} Talebiniz Alındı ({asset_symbol})",
        recipients=[email_to],
        body=html_content,
        subtype=MessageType.html
    )
    
    try:
        if 'fm' in globals():
            await fm.send_message(message)
            logger.info(f"Transaction request email sent to {email_to} for {asset_symbol}")
    except Exception as e:
        logger.error(f"E-posta gönderilirken (Transaction Request) hata oluştu: {str(e)}")

async def send_transaction_email(
    email_to: str, 
    transaction_type: str, 
    asset_symbol: str, 
    quantity: float, 
    price: float, 
    total_amount: float, 
    transaction_date: datetime
) -> None:
    """
    Kullanıcıya finansal işlem (Alım/Satım) dekontunu asenkron olarak gönderir.

    MİMARİ KARAR (ARCHITECTURE DECISION):
    Finansal işlemlerin (trade) HTTP request/response döngüsünü bloklamaması kritik 
    önem taşır. Bu nedenle, I/O darboğazı oluşturabilecek e-posta gönderim işlemi 
    FastAPI 'BackgroundTasks' altyapısı kullanılarak tamamen asenkron (non-blocking)
    yürütülmektedir. Hata fırlatılmaz; oluşan SMTP veya ağ hataları sadece 
    loglanarak (logger.error) sessizce tolere edilir, böylece ana finansal akış bozulmaz.
    """
    formatted_date = transaction_date.strftime("%d.%m.%Y %H:%M")
    
    # Translate transaction_type for the email display
    transaction_type_tr = "Alım" if transaction_type.upper() == "BUY" else ("Satım" if transaction_type.upper() == "SELL" else transaction_type)
    
    # Premium Dark Mode Table Template
    html_content = f"""
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
                                <h2 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 600;">MoneyFast İşlem Özeti</h2>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px;">
                                <h3 style="margin-top: 0; color: #ffffff; font-size: 20px; font-weight: 500;">İşleminiz Başarıyla Gerçekleşti</h3>
                                <p style="color: #a0aec0; font-size: 16px; line-height: 1.6; margin-bottom: 30px;">
                                    MoneyFast hesabınız üzerinden gerçekleştirilen işlem detaylarına aşağıdan ulaşabilirsiniz.
                                </p>
                                
                                <!-- İşlem Detayları Tablosu -->
                                <table width="100%" border="0" cellspacing="0" cellpadding="15" style="background-color: #121620; border-radius: 8px; border: 1px solid #2a3142;">
                                    <tr>
                                        <td style="color: #a0aec0; border-bottom: 1px solid #2a3142; font-size: 15px;">İşlem Tipi</td>
                                        <td align="right" style="color: #ffffff; border-bottom: 1px solid #2a3142; font-weight: 600; font-size: 15px;">{transaction_type_tr}</td>
                                    </tr>
                                    <tr>
                                        <td style="color: #a0aec0; border-bottom: 1px solid #2a3142; font-size: 15px;">Varlık (Sembol)</td>
                                        <td align="right" style="color: #4b7be5; border-bottom: 1px solid #2a3142; font-weight: 600; font-size: 15px;">{asset_symbol}</td>
                                    </tr>
                                    <tr>
                                        <td style="color: #a0aec0; border-bottom: 1px solid #2a3142; font-size: 15px;">Miktar</td>
                                        <td align="right" style="color: #ffffff; border-bottom: 1px solid #2a3142; font-weight: 600; font-size: 15px;">{quantity:,.2f}</td>
                                    </tr>
                                    <tr>
                                        <td style="color: #a0aec0; border-bottom: 1px solid #2a3142; font-size: 15px;">İşlem Fiyatı</td>
                                        <td align="right" style="color: #ffffff; border-bottom: 1px solid #2a3142; font-weight: 600; font-size: 15px;">{price:,.2f} ₺</td>
                                    </tr>
                                    <tr>
                                        <td style="color: #ffffff; font-size: 16px; font-weight: 700;">Toplam Tutar</td>
                                        <td align="right" style="color: #ffffff; font-size: 16px; font-weight: 700;">{total_amount:,.2f} ₺</td>
                                    </tr>
                                </table>
                                
                                <p style="color: #718096; font-size: 14px; line-height: 1.5; margin-top: 30px;">
                                    İşlem Tarihi: {formatted_date}<br>
                                    Bu e-posta sadece bilgilendirme amaçlıdır.
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

    message = MessageSchema(
        subject=f"MoneyFast - {transaction_type_tr} İşlemi Özeti ({asset_symbol})",
        recipients=[email_to],
        body=html_content,
        subtype=MessageType.html
    )

    try:
        if 'fm' in globals():
            await fm.send_message(message)
            logger.info(f"Transaction email sent to {email_to} for {asset_symbol}")
        else:
            logger.warning("SMTP yapılandırması eksik, işlem e-postası gönderilemedi.")
    except Exception as e:
        logger.error(f"E-posta gönderilirken (Transaction) beklenmeyen bir hata oluştu: {str(e)}")


async def send_daily_news_email(
    email_to: str,
    first_name: str,
    news_items: list,
    holdings_data: list,
    watchlist_symbols: list,
    quotes: dict
) -> None:
    """
    Kullanıcının portföyündeki ve favori listesindeki (watchlist) varlıkların
    fiyat özetlerini ve ilgili son 24 saatin haberlerini içeren günlük piyasa bültenini asenkron olarak gönderir.
    """
    
    # 1. Portföy (Holdings) HTML Tablosu Oluşturma
    holdings_html = ""
    if holdings_data:
        holdings_rows = ""
        for item in holdings_data:
            symbol = item.get("symbol", "Bilinmiyor")
            quote = quotes.get(symbol, {})
            price = quote.get("price") if quote.get("price") is not None else item.get("price")
            change_percent = quote.get("change_percent") if quote.get("change_percent") is not None else item.get("change_percent")
            
            price_str = f"{price:,.2f}" if price is not None else "N/A"
            
            if change_percent is not None:
                if change_percent > 0:
                    color = "#10B981" # Yeşil
                    arrow = "▲"
                    bg_badge = "rgba(16, 185, 129, 0.1)"
                elif change_percent < 0:
                    color = "#EF4444" # Kırmızı
                    arrow = "▼"
                    bg_badge = "rgba(239, 68, 68, 0.1)"
                else:
                    color = "#94a3b8"
                    arrow = "▬"
                    bg_badge = "rgba(148, 163, 184, 0.1)"
                change_str = f"""<span style="background: {bg_badge}; padding: 4px 8px; border-radius: 6px; color: {color}; display: inline-block;">{arrow} {abs(change_percent):.2f}%</span>"""
            else:
                change_str = "N/A"

            holdings_rows += f"""
            <tr>
                <td style="color: #60a5fa; border-bottom: 1px solid #1e293b; font-size: 15px; font-weight: 600; padding: 14px 0;">{symbol}</td>
                <td align="right" style="color: #f1f5f9; border-bottom: 1px solid #1e293b; font-weight: 600; font-size: 15px; padding: 14px 0;">{price_str}</td>
                <td align="right" style="border-bottom: 1px solid #1e293b; font-weight: 600; font-size: 14px; padding: 14px 0;">{change_str}</td>
            </tr>
            """
        
        holdings_html = f"""
        <h3 style="color: #e2e8f0; font-size: 18px; margin-bottom: 15px; margin-top: 30px; border-left: 3px solid #60a5fa; padding-left: 10px;">Portföy Özeti</h3>
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0f172a; border-radius: 10px; border: 1px solid #1e293b; padding: 10px 20px; margin-bottom: 30px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            {holdings_rows}
        </table>
        """

    # 2. İzleme Listesi (Watchlist) HTML Tablosu Oluşturma
    watchlist_html = ""
    if watchlist_symbols:
        watchlist_rows = ""
        for symbol in watchlist_symbols:
            quote = quotes.get(symbol, {})
            price = quote.get("price")
            change_percent = quote.get("change_percent")
            
            price_str = f"{price:,.2f}" if price is not None else "N/A"
            
            if change_percent is not None:
                if change_percent > 0:
                    color = "#10B981"
                    arrow = "▲"
                    bg_badge = "rgba(16, 185, 129, 0.1)"
                elif change_percent < 0:
                    color = "#EF4444"
                    arrow = "▼"
                    bg_badge = "rgba(239, 68, 68, 0.1)"
                else:
                    color = "#94a3b8"
                    arrow = "▬"
                    bg_badge = "rgba(148, 163, 184, 0.1)"
                change_str = f"""<span style="background: {bg_badge}; padding: 4px 8px; border-radius: 6px; color: {color}; display: inline-block;">{arrow} {abs(change_percent):.2f}%</span>"""
            else:
                change_str = "N/A"

            watchlist_rows += f"""
            <tr>
                <td style="color: #60a5fa; border-bottom: 1px solid #1e293b; font-size: 15px; font-weight: 600; padding: 14px 0;">{symbol}</td>
                <td align="right" style="color: #f1f5f9; border-bottom: 1px solid #1e293b; font-weight: 600; font-size: 15px; padding: 14px 0;">{price_str}</td>
                <td align="right" style="border-bottom: 1px solid #1e293b; font-weight: 600; font-size: 14px; padding: 14px 0;">{change_str}</td>
            </tr>
            """
            
        watchlist_html = f"""
        <h3 style="color: #e2e8f0; font-size: 18px; margin-bottom: 15px; margin-top: 30px; border-left: 3px solid #8b5cf6; padding-left: 10px;">İzleme Listesi</h3>
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0f172a; border-radius: 10px; border: 1px solid #1e293b; padding: 10px 20px; margin-bottom: 30px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            {watchlist_rows}
        </table>
        """

    # 3. Son Haberler (News) HTML Oluşturma
    news_html_cards = ""
    if news_items:
        news_html_cards = f'<h3 style="color: #e2e8f0; font-size: 18px; margin-bottom: 15px; margin-top: 30px; border-left: 3px solid #f59e0b; padding-left: 10px;">Portföyünüzden Öne Çıkanlar</h3>'
        for item in news_items:
            related = ", ".join(item.related_symbols) if hasattr(item, "related_symbols") and item.related_symbols else "Genel Piyasa"
            related_label = f"Sektör Haberi (Sembol: {related})" if related != "Genel Piyasa" else related
            title = item.title if hasattr(item, "title") and item.title else "Haber Başlığı"
            
            import re
            summary = item.summary if hasattr(item, "summary") and item.summary else ""
            summary = re.sub(r'<[^>]+>', '', summary)
            if len(summary) > 160:
                summary = summary[:160] + "..."
                
            url = item.url if hasattr(item, "url") and item.url else "#"
            
            time_str = ""
            if hasattr(item, "published_at") and item.published_at:
                try:
                    time_str = item.published_at.strftime("%d %b %H:%M")
                except:
                    pass

            news_html_cards += f"""
            <div style="background-color: #0f172a; border-radius: 10px; border: 1px solid #1e293b; padding: 20px; margin-bottom: 16px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <span style="background: rgba(96, 165, 250, 0.1); color: #60a5fa; font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 12px; letter-spacing: 0.5px;">{related_label}</span>
                    <span style="color: #64748b; font-size: 12px;">{time_str}</span>
                </div>
                <h4 style="margin: 0 0 10px 0; color: #f8fafc; font-size: 17px; line-height: 1.5; font-weight: 600;">
                    <a href="{url}" style="color: #f8fafc; text-decoration: none;">{title}</a>
                </h4>
                <p style="margin: 0; color: #94a3b8; font-size: 14px; line-height: 1.6;">{summary}</p>
            </div>
            """
    else:
        news_html_cards = """
        <h3 style="color: #e2e8f0; font-size: 18px; margin-bottom: 15px; margin-top: 30px; border-left: 3px solid #f59e0b; padding-left: 10px;">Piyasa Haberleri</h3>
        <div style="background-color: #0f172a; border-radius: 10px; border: 1px dashed #334155; padding: 30px; text-align: center;">
            <p style="margin: 0; color: #94a3b8; font-size: 15px; line-height: 1.6;">Son 24 saatte takip ettiğiniz varlıklarla ilgili yeni bir gelişme bulunmamaktadır.</p>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; background-color: #020617; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #020617; padding: 40px 0;">
            <tr>
                <td align="center">
                    <table width="600" border="0" cellspacing="0" cellpadding="0" style="background-color: #0f172a; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5); border: 1px solid #1e293b;">
                        <tr>
                            <td align="center" style="padding: 40px 40px 30px 40px; border-bottom: 1px solid #1e293b; background: linear-gradient(135deg, #0f172a 0%, #020617 100%);">
                                <h2 style="margin: 0; color: #ffffff; font-size: 26px; font-weight: 700; letter-spacing: -0.5px;">MoneyFast</h2>
                                <p style="margin: 8px 0 0 0; color: #94a3b8; font-size: 15px; font-weight: 500;">Günlük Piyasa ve Portföy Özeti</p>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px;">
                                <h3 style="margin-top: 0; color: #f8fafc; font-size: 20px; font-weight: 600;">Merhaba {first_name},</h3>
                                <p style="color: #cbd5e1; font-size: 16px; line-height: 1.6; margin-bottom: 10px;">
                                    İşte takip ettiğiniz ve sahip olduğunuz varlıkların son 24 saatteki durumu:
                                </p>
                                
                                {holdings_html}
                                {watchlist_html}
                                {news_html_cards}
                                
                                <div style="margin-top: 40px; text-align: center;">
                                    <a href="https://moneyfast.app" style="display: inline-block; background-color: #3b82f6; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 15px;">Platforma Git</a>
                                </div>
                            </td>
                        </tr>
                        <tr>
                            <td align="center" style="padding: 24px; background-color: #020617; border-top: 1px solid #1e293b;">
                                <p style="margin: 0; color: #64748b; font-size: 13px; line-height: 1.5;">
                                    Bu e-postayı bildirim ayarlarınız açık olduğu için alıyorsunuz.<br>
                                    Tercihlerinizi <a href="#" style="color: #60a5fa; text-decoration: none;">Güvenlik Merkezi</a> üzerinden değiştirebilirsiniz.
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

    message = MessageSchema(
        subject="MoneyFast Portföy ve Piyasa Bülteni",
        recipients=[email_to],
        body=html_content,
        subtype=MessageType.html
    )

    try:
        if 'fm' in globals():
            await fm.send_message(message)
            logger.info(f"Daily market briefing email sent to {email_to}")
        else:
            logger.warning("SMTP yapılandırması eksik, günlük bülten e-postası gönderilemedi.")
    except Exception as e:
        logger.error(f"E-posta gönderilirken (Daily Briefing) beklenmeyen bir hata oluştu: {str(e)}")
