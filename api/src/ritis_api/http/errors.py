from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ritis_api.domain.errors import BookingError
from ritis_api.ports.payments import PaymentProviderError
from ritis_api.ports.storage import BookingNotFoundError

log = logging.getLogger(__name__)


def install_error_handlers(app: FastAPI) -> None:
    """Domain and provider failures as HTTP answers with stable codes and no internals."""

    @app.exception_handler(BookingNotFoundError)
    async def not_found(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse({"detail": "booking_not_found"}, status_code=404)

    @app.exception_handler(BookingError)
    async def conflict(_: Request, exc: Exception) -> JSONResponse:
        log.info("booking conflict: %s", exc)
        return JSONResponse({"detail": "booking_conflict"}, status_code=409)

    @app.exception_handler(PaymentProviderError)
    async def provider_failed(_: Request, exc: Exception) -> JSONResponse:
        log.error("payment provider failed: %s", exc)
        return JSONResponse({"detail": "payment_provider_unavailable"}, status_code=502)
