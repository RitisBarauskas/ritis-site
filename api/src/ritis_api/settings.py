from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration from RITIS_* environment variables (locally: api/.env).

    Secrets come from Secret Manager in the cloud and never from the repository.
    """

    model_config = SettingsConfigDict(env_prefix="RITIS_", env_file=".env", extra="ignore")

    flitt_merchant_id: int
    flitt_secret_key: SecretStr
    flitt_base_url: str = "https://pay.flitt.com"
    # Public base URL of this API (the provider calls back here) and of the site.
    api_base_url: str
    site_url: str
    catalog_path: Path
    checkout_lifetime_seconds: int = Field(default=3600, ge=300, le=86400)
    http_timeout_seconds: float = Field(default=10.0, gt=0, le=30)
