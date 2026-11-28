from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from ritis_api.ports.payments import PaymentProviderError
from tests.fakes import FakeProvider
from tests.http.conftest import FORM, KEY, create, last_order


def test_create_returns_the_checkout_and_no_personal_data(client: TestClient) -> None:
    body = create(client)
    assert body["status"] == "awaiting_payment"
    assert (body["amount_minor"], body["currency"]) == (20000, "EUR")
    assert body["checkout_url"].startswith("https://pay.example/")
    assert set(body) == {
        "id",
        "status",
        "format",
        "amount_minor",
        "currency",
        "checkout_url",
        "can_retry_payment",
    }


def test_the_same_idempotency_key_gives_the_same_booking(
    client: TestClient, provider: FakeProvider
) -> None:
    assert create(client)["id"] == create(client)["id"]
    assert len(provider.checkout_requests) == 1


def test_the_same_key_with_other_data_is_refused(
    client: TestClient, provider: FakeProvider
) -> None:
    create(client)
    response = client.post(
        "/api/bookings", json={**FORM, "contact": "fixed@example.com"}, headers=KEY
    )
    assert (response.status_code, response.json()) == (422, {"detail": "idempotency_key_reused"})
    assert len(provider.checkout_requests) == 1


@pytest.mark.parametrize(
    ("change", "headers"),
    [
        ({}, {}),
        ({}, {"Idempotency-Key": "short"}),
        ({}, {"Idempotency-Key": "spaces are not allowed here"}),
        ({"consent": False}, KEY),
        ({"start_immediately": False}, KEY),
        ({"website": "http://spam.example"}, KEY),
        ({"format": "teardown"}, KEY),
        ({"price": 1}, KEY),
        ({"name": "   "}, KEY),
        ({"about": "x" * 2001}, KEY),
        ({"language": "de"}, KEY),
    ],
    ids=[
        "no-key",
        "short-key",
        "bad-key",
        "no-consent",
        "no-start-request",
        "honeypot",
        "free-format",
        "client-price",
        "blank-name",
        "long-about",
        "unknown-language",
    ],
)
def test_bad_requests_never_reach_the_provider(
    client: TestClient,
    provider: FakeProvider,
    change: dict[str, Any],
    headers: dict[str, str],
) -> None:
    response = client.post("/api/bookings", json={**FORM, **change}, headers=headers)
    assert response.status_code == 422
    assert provider.checkout_requests == []


def test_a_provider_outage_is_a_502(client: TestClient, provider: FakeProvider) -> None:
    provider.open_errors.append(PaymentProviderError("down"))
    response = client.post("/api/bookings", json=FORM, headers=KEY)
    assert (response.status_code, response.json()) == (
        502,
        {"detail": "payment_provider_unavailable"},
    )


def test_status_reflects_the_payment(client: TestClient, provider: FakeProvider) -> None:
    booking = create(client)
    provider.approve(last_order(provider))
    body = client.get(f"/api/bookings/{booking['id']}").json()
    assert (body["status"], body["checkout_url"], body["can_retry_payment"]) == (
        "paid",
        None,
        False,
    )


def test_unknown_and_malformed_booking_ids(client: TestClient) -> None:
    assert client.get("/api/bookings/" + "0" * 32).status_code == 404
    assert client.get("/api/bookings/not-an-id").status_code == 422


def test_pay_again_after_a_decline(client: TestClient, provider: FakeProvider) -> None:
    booking = create(client)
    provider.decline(last_order(provider))
    assert client.get(f"/api/bookings/{booking['id']}").json()["can_retry_payment"] is True

    again = client.post(f"/api/bookings/{booking['id']}/payments")
    assert again.status_code == 200
    assert again.json()["checkout_url"] not in (None, booking["checkout_url"])


def test_paying_a_paid_booking_again_is_a_conflict(
    client: TestClient, provider: FakeProvider
) -> None:
    booking = create(client)
    provider.approve(last_order(provider))
    assert client.get(f"/api/bookings/{booking['id']}").json()["status"] == "paid"
    response = client.post(f"/api/bookings/{booking['id']}/payments")
    assert (response.status_code, response.json()) == (409, {"detail": "booking_conflict"})


def test_no_public_api_docs(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_no_answer_of_the_api_may_be_cached(client: TestClient) -> None:
    # Firebase Hosting caches what is allowed to be cached; a booking's state never is.
    booking = create(client)
    answers = [
        client.get(f"/api/bookings/{booking['id']}"),
        client.get(f"/api/bookings/{'f' * 32}"),
        client.get("/api/payments/flitt/return"),
        client.get("/api/health"),
        client.post("/api/bookings", json={}, headers=KEY),
    ]

    assert [a.headers.get("cache-control") for a in answers] == ["no-store"] * len(answers)
