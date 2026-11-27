"""Composition root. Locally: uv run uvicorn ritis_api.main:build_app --factory --port 8000"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI

from ritis_api.adapters.flitt import FlittPaymentProvider
from ritis_api.adapters.log_notifier import LoggingNotifier
from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.app.catalog import load_catalog
from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.app.open_booking import CheckoutSettings, OpenBooking
from ritis_api.http.app import create_app
from ritis_api.settings import Settings


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # filled from RITIS_* environment variables
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    def clock() -> datetime:
        return datetime.now(UTC)

    def new_id() -> str:
        return uuid.uuid4().hex

    http = httpx.Client(timeout=httpx.Timeout(settings.http_timeout_seconds, connect=5.0))
    provider = FlittPaymentProvider.connect(
        http,
        merchant_id=settings.flitt_merchant_id,
        secret_key=settings.flitt_secret_key.get_secret_value(),
        base_url=settings.flitt_base_url,
    )
    # In-memory until Firestore: right for one local process, wrong for Cloud Run.
    repository = InMemoryBookingRepository()
    open_booking = OpenBooking(
        repository=repository,
        provider=provider,
        catalog=load_catalog(settings.catalog_path),
        settings=CheckoutSettings(
            api_base_url=settings.api_base_url,
            lifetime_seconds=settings.checkout_lifetime_seconds,
        ),
        clock=clock,
        new_id=new_id,
    )
    confirm_payment = ConfirmPayment(
        repository=repository, provider=provider, notifier=LoggingNotifier(), clock=clock
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        http.close()

    return create_app(
        open_booking=open_booking,
        confirm_payment=confirm_payment,
        provider=provider,
        site_url=settings.site_url,
        lifespan=lifespan,
    )
