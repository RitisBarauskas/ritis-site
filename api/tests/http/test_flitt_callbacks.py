from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeProvider
from tests.http.conftest import create, last_order

NOTIFICATION = "/api/payments/flitt/notification"


def test_a_signed_notification_records_the_payment(
    client: TestClient, provider: FakeProvider
) -> None:
    booking = create(client)
    provider.approve(last_order(provider))

    response = client.post(
        NOTIFICATION, json={"order_id": last_order(provider), "signature": "valid"}
    )
    assert (response.status_code, response.text) == (200, "OK")
    assert client.get(f"/api/bookings/{booking['id']}").json()["status"] == "paid"


def test_a_forged_notification_is_rejected_without_touching_the_order(
    client: TestClient, provider: FakeProvider
) -> None:
    create(client)
    provider.approve(last_order(provider))
    reports_before = provider.report_calls

    response = client.post(NOTIFICATION, json={"order_id": last_order(provider), "signature": "x"})
    assert response.status_code == 400
    assert provider.report_calls == reports_before


def test_a_signed_notification_for_a_stranger_order_is_acknowledged(client: TestClient) -> None:
    response = client.post(NOTIFICATION, json={"order_id": "not-ours", "signature": "valid"})
    assert response.status_code == 200


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_the_customer_returns_to_the_booking_page(
    client: TestClient, provider: FakeProvider, method: str
) -> None:
    booking = create(client)
    provider.approve(last_order(provider))
    reports_before = provider.report_calls

    response = client.request(
        method,
        f"/api/payments/flitt/return?booking={booking['id']}",
        # Flitt posts the order fields; the endpoint must not depend on them.
        data={"order_status": "approved", "signature": "whatever"} if method == "POST" else None,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"https://ritis.dev/booking/?id={booking['id']}"
    assert provider.report_calls == reports_before + 1, "the return re-checks the order"


@pytest.mark.parametrize("query", ["", "?booking=../../etc", "?booking=" + "0" * 32])
def test_a_return_without_a_known_booking(client: TestClient, query: str) -> None:
    response = client.get(f"/api/payments/flitt/return{query}")
    assert response.status_code == 303
    assert response.headers["location"] == "https://ritis.dev/booking/?error=not_found"
