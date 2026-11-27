from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ritis_api.app.open_booking import IdempotencyKeyReusedError
from ritis_api.domain.errors import BookingError
from ritis_api.http.errors import install_error_handlers
from ritis_api.ports.payments import PaymentProviderError
from ritis_api.ports.storage import BookingNotFoundError, ConcurrentModificationError


# The site tells failures apart by these codes (web/src/scripts/booking-api.ts), so renaming
# one is a breaking change for it.
@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (BookingNotFoundError("b1"), 404, "booking_not_found"),
        (IdempotencyKeyReusedError("k1"), 422, "idempotency_key_reused"),
        (BookingError("cannot be paid in paid"), 409, "booking_conflict"),
        (ConcurrentModificationError("b1"), 409, "booking_busy"),
        (PaymentProviderError("timeout"), 502, "payment_provider_unavailable"),
    ],
    ids=["not-found", "key-reused", "conflict", "busy", "provider-down"],
)
def test_each_failure_has_a_stable_code_and_no_internals(
    error: Exception, status: int, detail: str
) -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/fail")
    def fail() -> None:
        raise error

    response = TestClient(app).get("/fail")

    assert (response.status_code, response.json()) == (status, {"detail": detail})
