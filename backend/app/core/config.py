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

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
