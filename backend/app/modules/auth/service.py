from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    REFRESH_TOKEN_TYPE,
    VERIFICATION_TOKEN_TYPE,
    RESET_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    create_verification_token,
    create_reset_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.email import send_verification_email, send_password_reset_email
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    LoginRequest, 
    RegisterRequest, 
    TokenResponse, 
    UserResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserUpdateRequest,
    ChangePasswordRequest,
    DeleteAccountRequest
)


def authenticate_user(payload: LoginRequest, db: Session) -> TokenResponse:
    user = db.query(User).filter(User.tc_no == payload.tc_no).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TC Kimlik No veya şifre hatalı",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # GÜVENLİK: Kullanıcının e-posta adresi doğrulanmamışsa girişe izin verme.
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hesabınız doğrulanmamış. Lütfen e-postanıza gönderilen bağlantıya tıklayın.",
        )
    return TokenResponse(
        access_token=create_access_token(data={"sub": user.tc_no}),
        refresh_token=create_refresh_token(data={"sub": user.tc_no}),
    )


def refresh_access_token(refresh_token: str, db: Session) -> TokenResponse:
    """Yenileme token'ından yeni bir access token üretir.

    Sunulan token'ın gerçekten bir REFRESH token olması şart: aksi halde
    kısa ömürlü bir access token süresiz olarak kendini yenileyebilirdi ve
    kısa ömür anlamını kaybederdi.

    Kullanıcı hâlâ var ve aktif mi, her yenilemede yeniden denetlenir; devre
    dışı bırakılan bir hesabın oturumu bir sonraki yenilemede sona erer.
    """
    payload = decode_access_token(refresh_token)
    tc_no = payload.get("sub") if payload else None
    if not tc_no or payload.get("typ") != REFRESH_TOKEN_TYPE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yenileme token'ı geçersiz veya süresi dolmuş.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.tc_no == tc_no).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yenileme token'ı geçersiz veya süresi dolmuş.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Yeni bir refresh token verilmez: verilseydi oturum sonsuza kadar
    # uzatılabilirdi ve refresh token'ın süresi hiç dolmazdı.
    return TokenResponse(access_token=create_access_token(data={"sub": user.tc_no}))


def create_user(payload: RegisterRequest, db: Session, background_tasks: BackgroundTasks) -> UserResponse:
    existing_tc = db.query(User).filter(User.tc_no == payload.tc_no).first()
    if existing_tc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu TC Kimlik No ile zaten kayıt olunmuş.",
        )
        
    existing_email = db.query(User).filter(User.email == payload.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu E-posta adresi ile zaten kayıt olunmuş.",
        )
        
    user = User(
        tc_no=payload.tc_no,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        phone_number=payload.phone_number,
        hashed_password=hash_password(payload.password),
        is_verified=False,  # GÜVENLİK: Hesap oluşturulduğunda varsayılan olarak doğrulanmamış durumdadır.
    )
    db.add(user)
    # Flush rather than commit: the user id is needed to hang the investment
    # account off, and both rows should land in one transaction. A user
    # without an account cannot trade, and committing separately leaves that
    # state reachable if the second write fails.
    db.flush()

    # Modules call each other directly in this monolith; what stays inside the
    # owning module is the MODEL, not the behaviour (see CLAUDE.md).
    from app.modules.banking.service import ensure_account as ensure_bank_account
    from app.modules.investment.service import ensure_account

    ensure_account(db, str(user.id))
    # A deposit account too, so "para gönder" has somewhere to send from.
    ensure_bank_account(db, str(user.id))

    db.commit()
    db.refresh(user)
    
    # E-posta doğrulama token'ını oluştur ve gönder (Gerçek SMTP - Asenkron).
    token = create_verification_token(email=user.email)
    background_tasks.add_task(send_verification_email, user.email, token)
    
    return UserResponse.model_validate(user)


def verify_email(token: str, db: Session) -> dict:
    """
    Kullanıcının e-posta adresini, verilen JWT doğrulama token'ı ile doğrular.
    GÜVENLİK: Token'ın geçerliliği, süresi ve tipi (verification) kontrol edilir.
    """
    payload = decode_access_token(token)
    email = payload.get("sub") if payload else None
    
    if not email or payload.get("typ") != VERIFICATION_TOKEN_TYPE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doğrulama bağlantısı geçersiz veya süresi dolmuş.",
        )
        
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı.",
        )
        
    if user.is_verified:
        return {"message": "E-posta adresi zaten doğrulanmış."}
        
    user.is_verified = True
    db.commit()
    return {"message": "Hesabınız başarıyla doğrulandı. Şimdi giriş yapabilirsiniz."}


def send_password_reset(payload: ForgotPasswordRequest, db: Session, background_tasks: BackgroundTasks) -> dict:
    """
    Şifre sıfırlama işlemi için e-posta gönderir.
    GÜVENLİK: İşlemin onaylanması için TC Kimlik ve E-posta adresinin tamamen
    aynı kullanıcıya ait olması zorunludur.
    """
    user = db.query(User).filter(
        User.tc_no == payload.tc_no, 
        User.email == payload.email
    ).first()
    
    if not user:
        # GÜVENLİK: Sistemde hesap olup olmadığını belli etmemek için
        # genel bir başarı mesajı dönebilirsiniz. Fakat MoneyFast mimarisinde
        # kullanıcıyı uyarmak tercih edilmiş olabilir. 
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Verilen T.C. Kimlik No ve E-posta adresi eşleşmiyor veya kayıtlı değil.",
        )
        
    token = create_reset_token(email=user.email)
    background_tasks.add_task(send_password_reset_email, user.email, token)
    
    return {"message": "Şifre sıfırlama bağlantısı e-posta adresinize gönderildi."}


def reset_password(payload: ResetPasswordRequest, db: Session) -> dict:
    """
    Gelen JWT reset token'ına göre kullanıcının şifresini güvenli şekilde günceller.
    """
    decoded = decode_access_token(payload.token)
    email = decoded.get("sub") if decoded else None
    
    if not email or decoded.get("typ") != RESET_TOKEN_TYPE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Şifre sıfırlama bağlantısı geçersiz veya süresi dolmuş.",
        )
        
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı.",
        )
        
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    
    return {"message": "Şifreniz başarıyla sıfırlandı. Yeni şifrenizle giriş yapabilirsiniz."}


def update_user_profile(user_tc: str, payload: UserUpdateRequest, db: Session) -> UserResponse:
    """Kullanıcının profil bilgilerini ve ayarlarını günceller.
    GÜVENLİK: Yalnızca belirli alanların güncellenmesine izin verilir (email, telefon, bildirimler).
    TC kimlik no, ad, soyad değiştirilemez.
    """
    user = db.query(User).filter(User.tc_no == user_tc).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı.",
        )
    
    if payload.email is not None:
        # Aynı email'i kullanan başkası var mı kontrolü eklenebilir
        user.email = payload.email
    if payload.phone_number is not None:
        user.phone_number = payload.phone_number
    if payload.notification_preferences is not None:
        # JSONB alanı SQLAlchemy tarafından otomatik olarak json/dict nesnesine dönüştürülür
        user.notification_preferences = payload.notification_preferences
    if payload.transaction_limit is not None:
        # Güvenlik Merkezi → İşlem Onay Limiti değeri. Pydantic şemasında
        # [0, 250_000] aralığına kısıtlandığı için ek validasyona gerek yoktur.
        user.transaction_limit = payload.transaction_limit
    if payload.user_preferences is not None:
        # Görünüm & Format tercihleri (dil, para birimi, dashboard şablonu).
        # Mevcut JSONB içeriğiyle merge edilir: frontend yalnızca değişen
        # anahtarları gönderebilir, geri kalanı korunur.
        merged = {**(user.user_preferences or {}), **payload.user_preferences}
        user.user_preferences = merged

    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


def change_user_password(user_tc: str, payload: ChangePasswordRequest, db: Session) -> dict:
    """Mevcut kullanıcının şifresini değiştirir.
    GÜVENLİK: Mevcut şifrenin doğrulanması zorunludur.
    """
    user = db.query(User).filter(User.tc_no == user_tc).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı.",
        )
    
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mevcut şifre hatalı.",
        )
        
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    
    return {"message": "Şifreniz başarıyla değiştirildi."}


async def request_data_export(user_tc: str, db: Session, background_tasks: BackgroundTasks) -> dict:
    """Kullanıcının KVKK/GDPR kapsamındaki veri dışa aktarma talebini alır."""
    user = db.query(User).filter(User.tc_no == user_tc).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı.",
        )
    
    # Kullanıcı verilerini derle
    user_data = {
        "profile": {
            "tc_no": user.tc_no,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "user_preferences": getattr(user, 'user_preferences', {}),
            "notification_preferences": getattr(user, 'notification_preferences', {}),
        }
    }
    
    # Portföy Özetini Derle
    from app.modules.investment import market_service
    from app.modules.investment import ai_service
    
    rows = market_service.holdings(db, user_id=user.id)
    quotes = market_service.latest_quotes(db)
    rates = ai_service.fx_rates(quotes)
    account = market_service.account(db, user_id=user.id)
    
    cash = float(account.cash_balance) if account else 0.0
    bist = sum(
        value for value in (
            ai_service.holding_value(r, rates) for r in rows
            if (r.get("currency") or "TRY") == "TRY"
        ) if value is not None
    )
    foreign_try = sum(
        value for value in (
            ai_service.holding_value(r, rates) for r in rows
            if (r.get("currency") or "TRY") != "TRY"
        ) if value is not None
    )
    total_try = cash + bist + foreign_try
    
    portfolio_summary = {
        "cash": cash,
        "bist": bist,
        "us": foreign_try,
        "total_value": total_try,
    }
    
    from app.core.email import send_data_export_email
    background_tasks.add_task(send_data_export_email, user.email, user_data, portfolio_summary)
    
    return {
        "message": f"Veri dışa aktarma talebiniz alındı. Dosyanız hazırlanıp PDF olarak {user.email} adresine gönderilecektir."
    }

def deactivate_account(user_tc: str, reason: str | None, db: Session) -> dict:
    """Kullanıcı hesabını kalıcı olarak devre dışı bırakır (soft delete).

    GÜVENLİK & YASAL UYUM KARARI:
    Finansal düzenleme ve KVKK/MASAK yükümlülükleri gereği kullanıcı kaydı
    veritabanından fiziksel olarak silinmez (hard delete YASAKTIR). Bunun
    yerine `is_active` bayrağı False yapılır:
      1. Kullanıcı artık giriş yapamaz (`authenticate_user` bunu kontrol eder).
      2. Token yenileme reddedilir (`refresh_access_token` `is_active`'i denetler).
      3. Yasal inceleme gerektiren durumlarda veriler erişilebilir kalır.

    Opsiyonel olarak ayrılma nedeni kaydedilir; bu veri ürün analitiği ve
    kullanıcı kaybı (churn) analizleri için değerlidir.
    """
    user = db.query(User).filter(User.tc_no == user_tc).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı.",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bu hesap zaten devre dışı bırakılmış.",
        )
    
    user.is_active = False
    db.commit()
    
    # NOT: `reason` şu an loga yazılır; ileride ayrı bir `account_closures`
    # tablosuna kaydedilebilir.
    if reason:
        import logging
        logging.getLogger(__name__).info(
            f"Account deactivated: user={user.id}, reason={reason}"
        )
    
    return {"message": "Hesabınız başarıyla kapatıldı."}
