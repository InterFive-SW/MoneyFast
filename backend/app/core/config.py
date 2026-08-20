from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    AI_ORCHESTRATOR_URL: str = "http://agents:8080"

    model_config = {"env_file": ".env"}


settings = Settings()
