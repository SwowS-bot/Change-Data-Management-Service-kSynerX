import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="allow")

    PROJECT_NAME: str = "Change Data Management Service (CDMS)"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Database Settings (mapped to host port 5433 to avoid local 5432 conflict)
    POSTGRES_USER: str = "cdms_user"
    POSTGRES_PASSWORD: str = "cdms_password"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "5433"
    POSTGRES_DB: str = "cdms_db"
    
    # Async database URL (for asyncpg)
    ASYNC_DATABASE_URL: Optional[str] = None
    # Sync database URL (for psycopg2 / migrations / tests)
    SYNC_DATABASE_URL: Optional[str] = None
    
    # External Vietful Service (for Polling)
    VIETFUL_API_URL: str = "http://localhost:8001"
    POLLING_INTERVAL_SECONDS: int = 10

    @property
    def async_db_url(self) -> str:
        if self.ASYNC_DATABASE_URL:
            return self.ASYNC_DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_db_url(self) -> str:
        if self.SYNC_DATABASE_URL:
            return self.SYNC_DATABASE_URL
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

settings = Settings()
