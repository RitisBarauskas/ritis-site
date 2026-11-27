from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI

from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.app.open_booking import OpenBooking
from ritis_api.http.bookings import bookings_router
from ritis_api.http.errors import install_error_handlers
from ritis_api.http.flitt import flitt_router
from ritis_api.ports.payments import PaymentProvider

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_app(
    *,
    open_booking: OpenBooking,
    confirm_payment: ConfirmPayment,
    provider: PaymentProvider,
    site_url: str,
    lifespan: Lifespan | None = None,
) -> FastAPI:
    # No public OpenAPI docs: the only client is our own site.
    app = FastAPI(
        title="ritis-api", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(bookings_router(open_booking, confirm_payment))
    app.include_router(flitt_router(provider, confirm_payment, site_url))
    install_error_handlers(app)
    return app
