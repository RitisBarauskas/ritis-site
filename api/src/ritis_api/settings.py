from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ritis_api.adapters.flitt.client import BASE_URL as FLITT_BASE_URL

_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


class Settings(BaseSettings):
    """RITIS_* environment variables, locally from api/.env. Secrets never live in the repo."""

    # An unknown name in .env is a typo that would otherwise be silently ignored.
    model_config = SettingsConfigDict(env_prefix="RITIS_", env_file=".env", extra="forbid")

    flitt_merchant_id: int
    flitt_secret_key: SecretStr
    flitt_base_url: str = FLITT_BASE_URL
    # Public base URL of this API (Flitt calls back here) and of the site.
    api_base_url: str
    site_url: str
    catalog_path: Path
    checkout_lifetime_seconds: int = Field(default=3600, ge=300, le=86400)
    recheck_interval_seconds: float = Field(default=5.0, ge=1, le=60)
    http_timeout_seconds: float = Field(default=10.0, gt=0, le=30)

    @field_validator("flitt_base_url", "api_base_url", "site_url")
    @classmethod
    def _https_base_url(cls, value: str) -> str:
        parts = urlsplit(value)
        local = parts.scheme == "http" and parts.hostname in _LOOPBACK
        if not (parts.scheme == "https" or local) or not parts.hostname:
            raise ValueError("must be an https URL (http only for loopback)")
        if parts.query or parts.fragment:
            raise ValueError("must be a base URL without query or fragment")
        return value.rstrip("/")
