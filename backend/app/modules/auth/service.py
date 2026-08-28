from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.modules.auth.models import User
from app.modules.auth.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse


def authenticate_user(payload: LoginRequest, db: Session) -> TokenResponse:
    user = db.query(User).filter(User.tc_no == payload.tc_no).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TC Kimlik No veya şifre hatalı",
            headers={"WWW-Authenticate": "Bearer"},
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


def create_user(payload: RegisterRequest, db: Session) -> UserResponse:
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
    )
    db.add(user)
    # Flush rather than commit: the user id is needed to hang the investment
    # account off, and both rows should land in one transaction. A user
    # without an account cannot trade, and committing separately leaves that
    # state reachable if the second write fails.
    db.flush()

    # Modules call each other directly in this monolith; what stays inside the
    # owning module is the MODEL, not the behaviour (see CLAUDE.md).
    from app.modules.banking.service import (
        ensure_account as ensure_bank_account,
        ensure_savings_account,
    )
    from app.modules.investment.service import ensure_account

    ensure_account(db, str(user.id))
    # A deposit account too, so "para gönder" has somewhere to send from, and
    # a savings account so it has somewhere to send TO. With one account the
    # transfer screen could only ever send money away from the customer.
    ensure_bank_account(db, str(user.id))
    ensure_savings_account(db, str(user.id))

    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)
