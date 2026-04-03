from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "GSPS ERP"
    secret_key: str = "dev-secret-change-in-production"
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    access_token_expire_minutes: int = 60 * 24 * 7
    max_companies_per_user: int = 10

    # ZKTeco webhook integration (optional security).
    # If empty string, webhook requests are accepted without a secret header.
    zkteco_webhook_secret: str = ""
    # Public site URL for integration docs (webhooks). If empty, each request's Host is used.
    public_base_url: str = ""
    # Web UI clock display (IANA name). Stored timestamps remain UTC.
    display_timezone: str = "Asia/Kuala_Lumpur"


@lru_cache
def get_settings() -> Settings:
    return Settings()
