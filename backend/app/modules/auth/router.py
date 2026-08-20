"""
Kimlik Doğrulama API Router'ı

Kullanıcı kaydı, girişi ve profil bilgilerini getirme uç noktalarını tanımlar.
Veritabanı ekibi tarafından uygulanacak veritabanı işlemleri için yer tutucular içerir.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Body
from pydantic import EmailStr

from app.modules.auth import schemas, service
from app.core import deps
from app.core.database import get_db
from sqlalchemy.orm import Session
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    oauth2_scheme
)

# Profesyonel loglayıcıyı başlat
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])


@router.post(
    "/register", 
    response_model=schemas.UserResponse, 
    status_code=status.HTTP_201_CREATED,
    summary="Yeni bir kullanıcı kaydet"
)
async def register(user_in: schemas.RegisterRequest, db: Session = Depends(get_db)):
    """
    Girdilerini doğrulayarak ve şifrelerini güvenli bir şekilde hashleyerek yeni bir kullanıcı kaydeder.

    Kayıt artık gerçekten veritabanına yazıyor. Önceki yer tutucu, hiçbir şey
    kaydetmeden 201 ve rastgele bir UUID döndürüyordu; yani kayıt "başarılı"
    görünüyor ama ardından giriş yapılamıyordu.

    Şifre hash'leme ve tekillik kontrolleri `service.create_user` içinde.
    """
    return service.create_user(user_in, db)


@router.post(
    "/login", 
    response_model=schemas.TokenResponse,
    summary="Kullanıcıyı doğrula ve JWT token döndür"
)
async def login(credentials: schemas.LoginRequest, db: Session = Depends(get_db)):
    """
    TC ve şifresini doğrulayarak bir kullanıcıyı doğrular ve ardından bir JWT erişim token'ı verir.

    GÜVENLİK NOTU: Buradaki yer tutucu, veritabanına hiç bakmadan sabit
    "Password123" şifresini kabul ediyordu. Yani **herhangi bir TC numarası
    için** geçerli bir JWT üretiliyordu; `user_id` artık token'dan çözüldüğü
    için bu, başka bir kullanıcının portföyünü okumaya yeterdi. Gerçek
    doğrulama `service.authenticate_user` içinde ve zaten test edilmişti;
    çağrılmıyordu.
    """
    return service.authenticate_user(credentials, db)


@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    summary="Şifre sıfırlama bağlantısı iste"
)
async def forgot_password(email: EmailStr = Body(..., embed=True)):
    """
    Sağlanan e-postaya bir sıfırlama bağlantısı göndererek şifre sıfırlama sürecini başlatır.
    """
    # TODO: DB Mühendisi - E-postanın veritabanında olup olmadığını kontrol et.
    # Beklenen fonksiyon imzası: db_get_user_by_email(email: EmailStr)
    
    logger.info(f"Password reset link requested and dispatched for email: {email}")
    return {"message": "If the email is registered, a password reset link has been sent."}


@router.get(
    "/me", 
    response_model=schemas.UserResponse,
    summary="Mevcut doğrulanmış kullanıcı profilini getir"
)
async def get_current_user(user=Depends(deps.get_current_user)):
    """
    JWT token'ına dayanarak şu anda kimliği doğrulanmış kullanıcının profil
    bilgilerini getirir.

    Çözümleme `app/core/deps.py`'de; birden fazla modül aynı bağımlılığa
    ihtiyaç duyuyor (sohbet uç noktası `user_id`'yi oradan alıyor, çünkü MCP
    sözleşmesi bu değerin istemciden gelmesini yasaklıyor).

    Önceki hali her çağrıda rastgele bir UUID üreten bir yer tutucuydu; bu,
    aynı kullanıcının iki isteğinin farklı kimliklere sahip olması demekti ve
    konuşmaların bir kullanıcıya bağlanmasını imkânsız kılıyordu.
    """
    return user


@router.get(
    "/health",
    summary="Auth modülü sağlık durumu"
)
async def health_check():
    """
    Auth modülünün durumunu (health check) kontrol eder.
    Sistemin ayakta olup olmadığını ve doğru modüle ulaşıldığını doğrulamak için kullanılır.
    """
    return {"status": "ok", "module": "auth"}
