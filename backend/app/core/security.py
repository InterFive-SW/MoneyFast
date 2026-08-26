"""
Güvenlik ve Kimlik Doğrulama Araçları

Şifreleri hashlemek, kimlik bilgilerini doğrulamak ve API yetkilendirmesi için
JWT (JSON Web Token) vermek amacıyla profesyonel kriptografik araçlar sağlar.
"""
import jwt
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings

# bcrypt algoritmasını kullanarak CryptContext'i başlat.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Token çıkarmak için OAuth2 şemasını tanımla.
# tokenUrl, Swagger UI'a nerede kimlik doğrulaması yapılacağını bildirmek için login uç noktasına işaret eder.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    """
    Bcrypt kullanarak düz metin şifreden güvenli bir hash oluşturur.

    Args:
        password (str): Kullanıcı tarafından sağlanan düz metin şifre.

    Returns:
        str: Güvenli bir şekilde hashlenmiş şifre dizisi.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Düz metin bir şifreyi depolanmış bir hash ile doğrular.

    Args:
        plain_password (str): Giriş sırasında sağlanan düz metin şifre.
        hashed_password (str): Veritabanında depolanan bcrypt hash'i.

    Returns:
        bool: Şifre hash ile eşleşirse True, aksi takdirde False.
    """
    return pwd_context.verify(plain_password, hashed_password)


#: Token kind, carried as the `typ` claim.
#:
#: The two kinds are NOT interchangeable and the claim is what keeps them
#: apart. A refresh token lives for days; if it were accepted wherever an
#: access token is, a single leaked long-lived token would be as good as a
#: password. `get_current_user` rejects anything that is not ACCESS, and
#: `/auth/refresh` rejects anything that is not REFRESH.
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
VERIFICATION_TOKEN_TYPE = "verification"
RESET_TOKEN_TYPE = "reset"


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    Süre sonu (expiration) talebi içeren bir JSON Web Token (JWT) oluşturur.

    Args:
        data (dict): Token içine kodlanacak yük (payload).
        expires_delta (timedelta | None): İsteğe bağlı süre sonu süresi.
            Sağlanmazsa sistem yapılandırmasına varsayılan olarak ayarlanır.

    Returns:
        str: Kodlanmış JWT dizisi.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "typ": ACCESS_TOKEN_TYPE})

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Uzun ömürlü yenileme token'ı üretir.

    Yalnızca `/auth/refresh` tarafından kabul edilir; kaynak uç noktalarında
    kullanılamaz.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    to_encode.update({"exp": expire, "typ": REFRESH_TOKEN_TYPE})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_verification_token(email: str, expires_delta: timedelta | None = None) -> str:
    """
    E-posta doğrulama süreci için geçici bir JWT oluşturur.
    
    Bu token'ın 'typ' claim'i 'verification' olarak ayarlanır, böylece
    access veya refresh token olarak kullanılamaz.
    """
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=24))
    to_encode = {"sub": email, "exp": expire, "typ": VERIFICATION_TOKEN_TYPE}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_reset_token(email: str, expires_delta: timedelta | None = None) -> str:
    """
    Şifre sıfırlama süreci için geçici bir JWT oluşturur.
    
    Bu token'ın 'typ' claim'i 'reset' olarak ayarlanır, böylece
    diğer yetkilendirme süreçlerine dahil edilemez (GÜVENLİK).
    """
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=1))
    to_encode = {"sub": email, "exp": expire, "typ": RESET_TOKEN_TYPE}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Bir JSON Web Token'ını çözer ve doğrular.

    Args:
        token (str): Çözülecek JWT dizisi.

    Returns:
        dict: Çözülmüş token yükü. Doğrulama başarısız olursa boş bir sözlük döndürür.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return {}
