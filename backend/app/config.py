from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────
    APP_NAME: str = "Gema"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production-gema-secret-key"

    # ── Database ──────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://gema:gema_secret@db:5432/gema"
    SYNC_DATABASE_URL: str = "postgresql://gema:gema_secret@db:5432/gema"

    # ── Redis ─────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"

    # ── MongoDB (vector store) ────────────────────────────────────────
    MONGODB_URL: str = "mongodb://mongo:27017/?directConnection=true"
    MONGODB_DB: str = "gema"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSIONS: int = 384

    # ── AI Provider Keys ──────────────────────────────────────────────
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    MISTRAL_API_KEY: Optional[str] = None
    COHERE_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    TOGETHER_API_KEY: Optional[str] = None
    HUGGINGFACE_API_KEY: Optional[str] = None
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_ENDPOINT: Optional[str] = None
    AZURE_OPENAI_DEPLOYMENT: Optional[str] = None

    # ── Security ──────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = ["*"]
    GEMA_API_KEY: Optional[str] = None

    # ── Storage ───────────────────────────────────────────────────────
    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # ── Postgres env vars (used in docker-compose) ────────────────────
    POSTGRES_USER: str = "gema"
    POSTGRES_PASSWORD: str = "gema_secret"
    POSTGRES_DB: str = "gema"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
