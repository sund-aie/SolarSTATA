"""Runtime configuration. Reads SOLARSTATA_* environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SOLARSTATA_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000

    # Cookie-signed session id. Override in production.
    session_secret: str = "dev-only-replace-in-prod"
    session_cookie_name: str = "solarstata_session"
    session_idle_timeout_seconds: int = 24 * 60 * 60  # 24h
    session_eviction_interval_seconds: int = 5 * 60   # 5min

    # Upload limits
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]


settings = Settings()
