from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    #: Refresh token lifetime. The access token stays short because it is sent
    #: on every request; the refresh token is what keeps a session alive past
    #: 30 minutes. Before it existed, an expired session did not log the user
    #: out -- it silently degraded them to an anonymous caller, and the chat
    #: went on staging trades that could never be confirmed.
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    AI_ORCHESTRATOR_URL: str = "http://agents:8080"
    #: Yüklenen belgeler buraya gömülüyor. Backend'in vektör veritabanı
    #: kredensiyeli YOK ve olmamalı (bkz. CLAUDE.md): `rag` servisi onu tutan
    #: tek bileşen, dolayısıyla yükleme de arama gibi HTTP üzerinden gidiyor.
    RAG_URL: str = "http://rag:8100"

    # --- SMTP -------------------------------------------------------------
    #
    # E-posta gönderimi `core/email.py` içinde ve değerleri `os.getenv` ile
    # okuyor. Bu alanlar yine de burada TANIMLI, çünkü tanımlı bir alan
    # tiplenmiş ve varsayılanı görünür oluyor: `SMTP_PORT` bir `int` ve
    # `.env`'de "beşyüzseksenyedi" yazan biri açılışta öğreniyor.
    #
    # Varsayılanlar `.env.example` ile aynı. Kimlik bilgileri BOŞ: gerçek bir
    # parolayı depoya varsayılan olarak koymak, onu depoya koymaktır.
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@moneyfast.com"

    # `extra: ignore` main'den geliyor ve KALIYOR. İkimiz de aynı duvara
    # çarptık: pydantic-settings varsayılanı `.env` dosyasındaki tanımsız bir
    # anahtarı `extra_forbidden` ile reddediyor, yani `.env.example`'ı
    # belgelendiği gibi doldurmak uygulamayı hiç açtırmıyordu -- hatanın metni
    # ("Extra inputs are not permitted") sebebi de göstermiyordu.
    #
    # Konteynerde görünmüyor: orada `/app/.env` yok, değerler compose'un
    # `env_file` ayarıyla gerçek ortam değişkeni olarak geliyor. Testler ise
    # depoyu bağlıyor ve dosya orada.
    #
    # Bedeli, `SECRET_KEYY=` gibi bir yazım hatasının sessizce yutulması. Buna
    # karşılık `.env` kişi başına bir dosya ve başka bir yerde `os.getenv` ile
    # okunan değişkenleri de taşıyabiliyor; `forbid` bırakmak, birinin kendi
    # dosyasına eklediği ilgisiz bir satırın herkesin uygulamasını açılmaz
    # yapması demekti.
    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
