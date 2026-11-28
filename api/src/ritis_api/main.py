from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import FastAPI
from google.cloud import firestore

from ritis_api.adapters.firestore import FirestoreBookingRepository
from ritis_api.adapters.flitt import FlittNotifications, FlittPaymentProvider
from ritis_api.adapters.log_notifier import LoggingNotifier
from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.adapters.telegram import TelegramNotifier
from ritis_api.app.catalog import load_catalog
from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.app.deliver_notices import DeliverNotices
from ritis_api.app.open_booking import OpenBooking
from ritis_api.http.app import create_app
from ritis_api.http.flitt import flitt_checkout_settings
from ritis_api.ports.notifications import Notifier
from ritis_api.ports.storage import BookingRepository
from ritis_api.settings import Settings


def build_app(settings: Settings | None = None) -> FastAPI:
    """The composition root: the only place that knows every concrete adapter."""
    settings = settings or Settings()  # filled from RITIS_* environment variables
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # httpx logs every request URL at INFO, and the Telegram bot token is part of its URL.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    def clock() -> datetime:
        return datetime.now(UTC)

    def new_id() -> str:
        return uuid.uuid4().hex

    secret = settings.flitt_secret_key.get_secret_value()
    http = httpx.Client(timeout=httpx.Timeout(settings.http_timeout_seconds, connect=5.0))
    provider = FlittPaymentProvider.connect(
        http,
        merchant_id=settings.flitt_merchant_id,
        secret_key=secret,
        base_url=settings.flitt_base_url,
    )
    repository = _repository(settings)
    deliver_notices = DeliverNotices(repository=repository, notifier=_notifier(settings, http))
    confirm_payment = ConfirmPayment(
        repository=repository,
        provider=provider,
        notices=deliver_notices,
        clock=clock,
        recheck_interval=timedelta(seconds=settings.recheck_interval_seconds),
    )
    open_booking = OpenBooking(
        repository=repository,
        provider=provider,
        confirm_payment=confirm_payment,
        catalog=load_catalog(settings.catalog_path),
        settings=flitt_checkout_settings(
            settings.api_base_url, lifetime_seconds=settings.checkout_lifetime_seconds
        ),
        clock=clock,
        new_id=new_id,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        http.close()

    return create_app(
        open_booking=open_booking,
        confirm_payment=confirm_payment,
        flitt_notifications=FlittNotifications.for_merchant(
            merchant_id=settings.flitt_merchant_id, secret_key=secret
        ),
        deliver_notices=deliver_notices,
        site_url=settings.site_url,
        sweep_token=settings.sweep_token.get_secret_value() if settings.sweep_token else None,
        lifespan=lifespan,
    )


def _repository(settings: Settings) -> BookingRepository:
    if settings.storage == "firestore":
        return FirestoreBookingRepository(firestore.Client(database=settings.firestore_database))
    return InMemoryBookingRepository()


def _notifier(settings: Settings, http: httpx.Client) -> Notifier:
    if settings.telegram_bot_token is None or settings.telegram_chat_id is None:
        return LoggingNotifier()
    return TelegramNotifier(
        http,
        token=settings.telegram_bot_token.get_secret_value(),
        chat_id=settings.telegram_chat_id,
    )
