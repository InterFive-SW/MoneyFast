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
    """
    # Düz metin şifreyi güvenli bir şekilde hashle
    hashed_password = hash_password(user_in.password)
    
    # TODO: DB Mühendisi - Kullanıcı oluşturma mantığını burada uygula.
    # Veritabanı bağlandığında aşağıdaki satırı aktif edin ve mock kodları silin:
    # return service.create_user(user_in, db)
    
    # --- YER TUTUCU SİMÜLASYONU (DB bağlandığında kaldırın) ---
    import uuid
    simulated_user = {
        "id": str(uuid.uuid4()),
        "first_name": user_in.first_name,
        "last_name": user_in.last_name,
        "tc_no": user_in.tc_no,
        "email": user_in.email,
        "phone_number": user_in.phone_number,
        "is_active": True,
        "created_at": datetime.now(timezone.utc)
    }
    logger.info(f"User registration simulated for {user_in.email}")
    return simulated_user


@router.post(
    "/login", 
    response_model=schemas.TokenResponse,
    summary="Kullanıcıyı doğrula ve JWT token döndür"
)
async def login(credentials: schemas.LoginRequest, db: Session = Depends(get_db)):
    """
    TC ve şifresini doğrulayarak bir kullanıcıyı doğrular ve ardından bir JWT erişim token'ı verir.
    """
    # TODO: DB Mühendisi - Kullanıcı alma mantığını burada uygula.
    # Veritabanı bağlandığında aşağıdaki satırı aktif edin ve mock kodları silin:
    # return service.authenticate_user(credentials, db)
    
    # --- YER TUTUCU SİMÜLASYONU (DB bağlandığında kaldırın) ---
    # Gösterim için, "Password123" şifresine sahip simüle edilmiş bir kullanıcının var olduğunu varsayıyoruz
    simulated_hashed_password = hash_password("Password123")
    simulated_db_user = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "tc_no": credentials.tc_no,
        "hashed_password": simulated_hashed_password
    }
    
    # 1. Kullanıcının olup olmadığını kontrol et (Simüle edilmiş: tc_no yanlış değilse kullanıcının her zaman var olduğunu varsay)
    # 2. Şifreyi doğrula
    if not verify_password(credentials.password, simulated_db_user["hashed_password"]):
        logger.warning(f"Failed login attempt for TC: {credentials.tc_no}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # JWT token'ı oluştur
    access_token = create_access_token(data={"sub": str(simulated_db_user["tc_no"])})
    logger.info(f"User {credentials.tc_no} logged in successfully.")
    
    return {"access_token": access_token, "token_type": "bearer"}


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
async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    JWT token'ına dayanarak şu anda kimliği doğrulanmış kullanıcının profil bilgilerini getirir.
    """
    payload = decode_access_token(token)
    tc_no: str = payload.get("sub")
    
    if tc_no is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # TODO: DB Mühendisi - Çıkarılan tc_no'yu kullanarak kullanıcıyı veritabanından getir.
    # Beklenen fonksiyon imzası: db_get_user_by_tc_no(tc_no: str)
    # Kullanıcı ORM örneğini döndür. Kullanıcı bulunamazsa 401 hatası fırlat.
    
    # --- YER TUTUCU SİMÜLASYONU (DB bağlandığında kaldırın) ---
    import uuid
    simulated_user = {
        "id": str(uuid.uuid4()),
        "first_name": "Simulated",
        "last_name": "User",
        "tc_no": tc_no,
        "email": "simulated@example.com",
        "phone_number": "+905554443322",
        "is_active": True,
        "created_at": datetime.now(timezone.utc)
    }
    return simulated_user
