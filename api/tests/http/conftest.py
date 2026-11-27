from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from ritis_api.app.confirm_payment import ConfirmPayment
from ritis_api.app.open_booking import OpenBooking
from ritis_api.domain.identifiers import OrderId
from ritis_api.http.app import create_app
from tests.fakes import FakeProvider

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
    open_booking: OpenBooking, confirm_payment: ConfirmPayment, provider: FakeProvider
) -> TestClient:
    app = create_app(
        open_booking=open_booking,
        confirm_payment=confirm_payment,
        provider=provider,
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
