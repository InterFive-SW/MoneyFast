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
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_password_hash(password: str) -> str:
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
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


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
