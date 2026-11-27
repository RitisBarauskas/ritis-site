from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from ritis_api.adapters.flitt import FlittNotifications
from ritis_api.adapters.flitt.signature import FlittSigner
from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.domain.identifiers import OrderId
from ritis_api.http.app import create_app
from ritis_api.http.flitt import flitt_checkout_settings
from tests.conftest import make_open_booking
from tests.fakes import Clock, FakeProvider

MERCHANT_ID = 1549901
SIGNER = FlittSigner("test")
KEY = {"Idempotency-Key": "key-0000000000000001"}
FORM: dict[str, Any] = {
    "format": "foundation",
    "name": "Анна",
    "contact": "client@example.com",
    "about": "MVP на FastAPI",
    "links": "",
    "consent": True,
}


@pytest.fixture
def client(
    repository: InMemoryBookingRepository,
    provider: FakeProvider,
    confirm_payment: ConfirmPayment,
    clock: Clock,
) -> TestClient:
    # The same URL builder as the composition root, so the URLs handed out match the routes.
    settings = flitt_checkout_settings("https://ritis.dev", lifetime_seconds=3600)
    app = create_app(
        open_booking=make_open_booking(repository, provider, clock, settings),
        confirm_payment=confirm_payment,
        flitt_notifications=FlittNotifications(SIGNER, merchant_id=MERCHANT_ID),
        site_url="https://ritis.dev/",
    )
    return TestClient(app, follow_redirects=False)


def create(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/bookings", json=FORM, headers=KEY)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def last_order(provider: FakeProvider) -> OrderId:
    return provider.checkout_requests[-1].order_id


def signed_notification(order_id: str, **fields: Any) -> dict[str, Any]:
    payload = {
        "order_id": order_id,
        "merchant_id": MERCHANT_ID,
        "order_status": "approved",
        **fields,
    }
    payload["signature"] = SIGNER.sign(payload)
    return payload
