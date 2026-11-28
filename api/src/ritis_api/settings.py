from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ritis_api.adapters.flitt.client import BASE_URL as FLITT_BASE_URL

_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


class Settings(BaseSettings):
    """RITIS_* environment variables, locally from api/.env. Secrets never live in the repo."""

    # An unknown name in .env is a typo that would otherwise be silently ignored; for the
    # environment itself see _no_unknown_ritis_variables.
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
    # Where bookings live: process memory for one local process, Firestore for Cloud Run. The
    # Firestore project comes from the environment (GOOGLE_CLOUD_PROJECT or the credentials).
    storage: Literal["memory", "firestore"] = "memory"
    firestore_database: str = "(default)"
    # The owner hears about payments and flags from the site's bot; without these, the log.
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: int | None = None
    # What Cloud Scheduler presents to sweep undelivered notices; without it there is no sweep.
    sweep_token: SecretStr | None = Field(default=None, min_length=32)

    @model_validator(mode="after")
    def _telegram_whole(self) -> Settings:
        if (self.telegram_bot_token is None) != (self.telegram_chat_id is None):
            raise ValueError("Telegram needs both the bot token and the chat id")
        return self

    @model_validator(mode="after")
    def _production_on_cloud_run(self) -> Settings:
        # Cloud Run sets K_SERVICE. Its instances share no memory: a booking made on one would
        # be missing on the next. And a log nobody reads is no way to hear about a payment.
        if not os.environ.get("K_SERVICE"):
            return self
        if self.storage == "memory":
            raise ValueError("in-memory storage on Cloud Run: set RITIS_STORAGE=firestore")
        if self.telegram_bot_token is None or self.sweep_token is None:
            raise ValueError("on Cloud Run the owner is told through Telegram, swept by Scheduler")
        return self

    @model_validator(mode="after")
    def _no_unknown_ritis_variables(self) -> Settings:
        # Environment variables are read for known fields only, so a misspelt one (in Cloud Run)
        # would be skipped silently and its default used instead.
        known = {f"RITIS_{name}".upper() for name in type(self).model_fields}
        unknown = sorted(
            name
            for name in os.environ
            if name.upper().startswith("RITIS_") and name.upper() not in known
        )
        if unknown:
            raise ValueError(f"unknown settings in the environment: {', '.join(unknown)}")
        return self

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
