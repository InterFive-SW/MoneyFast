"""
Kimlik Doğrulama API Router'ı

Kullanıcı kaydı, girişi ve profil bilgilerini getirme uç noktalarını tanımlar.
Veritabanı ekibi tarafından uygulanacak veritabanı işlemleri için yer tutucular içerir.
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Body, BackgroundTasks
from pydantic import EmailStr

from app.modules.auth import schemas, service
from app.modules.auth.schemas import (
    ForgotPasswordRequest, 
    ResetPasswordRequest, 
    VerifyEmailRequest,
    UserUpdateRequest,
    ChangePasswordRequest,
    DeleteAccountRequest
)
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
async def register(user_in: schemas.RegisterRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Girdilerini doğrulayarak ve şifrelerini güvenli bir şekilde hashleyerek yeni bir kullanıcı kaydeder.

    Kayıt artık gerçekten veritabanına yazıyor. Önceki yer tutucu, hiçbir şey
    kaydetmeden 201 ve rastgele bir UUID döndürüyordu; yani kayıt "başarılı"
    görünüyor ama ardından giriş yapılamıyordu.

    Şifre hash'leme ve tekillik kontrolleri `service.create_user` içinde.
    """
    return service.create_user(user_in, db, background_tasks)


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
    "/refresh",
    response_model=schemas.TokenResponse,
    summary="Yenileme token'ı ile yeni bir access token al",
)
async def refresh(payload: schemas.RefreshRequest, db: Session = Depends(get_db)):
    """
    Süresi dolmuş bir access token'ı, uzun ömürlü yenileme token'ıyla tazeler.

    Bu uç nokta olmadan oturum 30 dakikada sessizce düşüyordu: kullanıcı
    çıkışa yönlendirilmiyor, anonim çağırana dönüşüyordu. Sohbet çalışmaya
    devam ettiği için fark edilmiyordu, ama hazırladığı işlem önerileri
    `user_id="anonymous"` ile kaydediliyor ve onay adımında kalıcı olarak
    404 alıyordu.
    """
    return service.refresh_access_token(payload.refresh_token, db)


@router.post(
    "/verify-email",
    status_code=status.HTTP_200_OK,
    summary="E-posta adresini doğrula"
)
async def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)):
    """
    Kullanıcının e-posta adresini JWT token üzerinden doğrular.
    GÜVENLİK: Sadece geçerli ve süresi dolmamış tokenlar kabul edilir.
    """
    return service.verify_email(payload.token, db)


@router.post(
    "/forgot-password",
    status_code=status.HTTP_200_OK,
    summary="Şifre sıfırlama bağlantısı iste"
)
async def forgot_password(payload: ForgotPasswordRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Kullanıcıya e-posta yoluyla şifre sıfırlama bağlantısı gönderir.
    GÜVENLİK: TC Kimlik ve E-posta doğrulaması yapılarak yetkisiz erişim önlenir.
    """
    logger.info(f"Password reset request received for email: {payload.email}")
    return service.send_password_reset(payload, db, background_tasks)


@router.post(
    "/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Yeni şifre belirle"
)
async def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Geçerli bir şifre sıfırlama token'ı ile kullanıcının şifresini yeniler.
    GÜVENLİK: JWT token'ı doğrulanır, şifre bcrypt ile hashlenerek saklanır.
    """
    return service.reset_password(payload, db)


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
    payload = schemas.UserResponse.model_validate(user)
    payload.customer_no = service.customer_no_for(user.id)
    return payload


@router.put(
    "/me",
    response_model=schemas.UserResponse,
    summary="Mevcut kullanıcının profilini güncelle"
)
async def update_profile(
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    user=Depends(deps.get_current_user)
):
    """
    Kullanıcının kendi profil bilgilerini ve ayarlarını günceller.
    GÜVENLİK: Yalnızca yetkili alanlar (e-posta, telefon, bildirimler vb.) güncellenir.
    """
    return service.update_user_profile(user.tc_no, payload, db)


@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK,
    summary="Kullanıcının şifresini değiştir"
)
async def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user=Depends(deps.get_current_user)
):
    """
    Aktif oturumu olan kullanıcının şifresini güvenli bir şekilde değiştirir.
    GÜVENLİK: Mevcut şifrenin uyuştuğu servis katmanında teyit edilir.
    """
    return service.change_user_password(user.tc_no, payload, db)


@router.post(
    "/export-data",
    status_code=status.HTTP_200_OK,
    summary="KVKK/GDPR veri dışa aktarma talebi oluştur"
)
async def export_data(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(deps.get_current_user)
):
    """Kullanıcının tüm kişisel verilerinin dışa aktarılması talebini alır.

    KVKK/GDPR UYUM:
    6698 sayılı KVKK ve AB Genel Veri Koruma Tüzüğü (GDPR) kapsamında
    kullanıcılar, platformda saklanan tüm kişisel verilerinin makine
    tarafından okunabilir bir formatta (JSON/CSV/ZIP) kendilerine
    teslim edilmesini talep etme hakkına sahiptir. Bu endpoint o
    talebi başlatır; dosya hazırlandığında kullanıcının kayıtlı
    e-posta adresine gönderilir.
    """
    return await service.request_data_export(user.tc_no, db, background_tasks)


@router.delete(
    "/me",
    status_code=status.HTTP_200_OK,
    summary="Kullanıcı hesabını kalıcı olarak kapat (soft delete)"
)
async def delete_account(
    payload: DeleteAccountRequest,
    db: Session = Depends(get_db),
    user=Depends(deps.get_current_user)
):
    """Kullanıcı hesabını kalıcı olarak devre dışı bırakır.

    GÜVENLİK & MİMARİ KARAR:
    Bu endpoint, kullanıcı kaydını veritabanından SILMEZ (hard delete).
    Bunun yerine `is_active=False` yaparak (soft delete) hesabı devre
    dışı bırakır. Bu yaklaşım:
      • MASAK ve finansal düzenleme uyumunu korur (işlem geçmişi saklı kalır).
      • Kullanıcının tekrar giriş yapmasını engeller.
      • Yasal inceleme durumunda verilerin erişilebilir kalmasını sağlar.

    Frontend'de çok adımlı onay modalı ("KAPAT" yazma zorunluluğu) ile
    korunur; yetkisiz veya kazara tetiklenmesi önlenir.
    """
    return service.deactivate_account(user.tc_no, payload.reason, db)


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
