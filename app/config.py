from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DOCUMENT_SERVICE_URL: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    DATABASE_URL: str
    DEBUG: bool = False  # Default value if missing

    class Config:
        env_file = ".env"  # Optional (Pydantic auto-finds .env)
        env_file_encoding = "utf-8"  # For non-ASCII .env files


settings = Settings()  # Loads from .env automatically
