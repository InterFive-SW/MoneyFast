from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
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
    token = create_access_token(data={"sub": user.tc_no})
    return TokenResponse(access_token=token)


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
    from app.modules.banking.service import ensure_account as ensure_bank_account
    from app.modules.investment.service import ensure_account

    ensure_account(db, str(user.id))
    # A deposit account too, so "para gönder" has somewhere to send from.
    ensure_bank_account(db, str(user.id))

    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)
