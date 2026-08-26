"""
Mock Email Servisi

Gerçek bir SMTP sunucusu olmadığı için geliştirme aşamasında e-postaları
terminal loglarına yazar. İleride SendGrid veya AWS SES gibi bir servis 
entegre edildiğinde bu modül güncellenmelidir.
"""
import logging

logger = logging.getLogger(__name__)

def send_verification_email(email: str, token: str) -> None:
    """
    Kullanıcıya e-posta doğrulama linki gönderir (Loglara basar).
    """
    verification_url = f"http://localhost:3000/verify-email?token={token}"
    
    logger.info("="*50)
    logger.info(f"EMAIL GÖNDERİLİYOR -> ALICI: {email}")
    logger.info("Konu: MoneyFast - E-posta Doğrulama")
    logger.info(f"İçerik: Hesabınızı doğrulamak için lütfen aşağıdaki bağlantıya tıklayın:\n{verification_url}")
    logger.info("="*50)


def send_password_reset_email(email: str, token: str) -> None:
    """
    Kullanıcıya şifre sıfırlama linki gönderir (Loglara basar).
    """
    reset_url = f"http://localhost:3000/reset-password?token={token}"
    
    logger.info("="*50)
    logger.info(f"EMAIL GÖNDERİLİYOR -> ALICI: {email}")
    logger.info("Konu: MoneyFast - Şifre Sıfırlama")
    logger.info(f"İçerik: Şifrenizi sıfırlamak için lütfen aşağıdaki bağlantıya tıklayın:\n{reset_url}")
    logger.info("="*50)
