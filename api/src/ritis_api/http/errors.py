from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ritis_api.app.open_booking import IdempotencyKeyReusedError
from ritis_api.domain.errors import BookingError
from ritis_api.ports.payments import PaymentProviderError
from ritis_api.ports.storage import BookingNotFoundError, ConcurrentModificationError

log = logging.getLogger(__name__)


def install_error_handlers(app: FastAPI) -> None:
    """Domain and provider failures as HTTP answers with stable codes and no internals."""

    def answer(detail: str, status_code: int) -> JSONResponse:
        return JSONResponse({"detail": detail}, status_code=status_code)

    @app.exception_handler(BookingNotFoundError)
    async def not_found(_: Request, __: Exception) -> JSONResponse:
        return answer("booking_not_found", 404)

    @app.exception_handler(IdempotencyKeyReusedError)
    async def key_reused(_: Request, __: Exception) -> JSONResponse:
        return answer("idempotency_key_reused", 422)

    @app.exception_handler(BookingError)
    async def conflict(_: Request, exc: Exception) -> JSONResponse:
        log.info("booking conflict: %s", exc)
        return answer("booking_conflict", 409)

    @app.exception_handler(ConcurrentModificationError)
    async def busy(_: Request, exc: Exception) -> JSONResponse:
        log.warning("booking kept changing under us: %s", exc)
        return answer("booking_busy", 409)

    @app.exception_handler(PaymentProviderError)
    async def provider_failed(_: Request, exc: Exception) -> JSONResponse:
        log.error("payment provider failed: %s", exc)
        return answer("payment_provider_unavailable", 502)
