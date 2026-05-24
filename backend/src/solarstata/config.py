"""Runtime configuration. Reads SOLARSTATA_* environment variables."""

from __future__ import annotations

from pydantic import AliasChoices, Field
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

    # CORS — both localhost and 127.0.0.1 variants. The Electron
    # desktop shell loads the renderer at http://127.0.0.1:5173 so
    # it shares a host with the sidecar; the localhost forms remain
    # for plain browser dev (Vite proxy on :5173, alternative :3000).
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    # Single-user desktop build. Enabled by the Electron sidecar spawn,
    # which sets SOLARSTATA_DESKTOP=1. NB: under env_prefix the bare
    # field would resolve to SOLARSTATA_DESKTOP_MODE, which is NOT what
    # the shell sets — that mismatch silently left this False and broke
    # the packaged app (file:// renderer can't send the SameSite session
    # cookie cross-origin to the 127.0.0.1 sidecar, so without the
    # singleton every request gets a fresh session and frames vanish).
    # Alias explicitly to the name the shell sets; accept the prefixed
    # form too for robustness. When on, SessionMiddleware routes every
    # request to one in-memory session regardless of cookie.
    desktop_mode: bool = Field(
        default=False,
        validation_alias=AliasChoices("SOLARSTATA_DESKTOP", "SOLARSTATA_DESKTOP_MODE"),
    )


settings = Settings()
