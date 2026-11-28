from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from ritis_api.http.flitt import NOTIFICATION_PATH
from ritis_api.ports.payments import PaymentProviderError
from tests.fakes import FakeProvider
from tests.http.conftest import FORM, KEY, create, last_order, signed_notification


def test_a_signed_notification_records_the_payment(
    client: TestClient, provider: FakeProvider
) -> None:
    booking = create(client)
    provider.approve(last_order(provider))

    response = client.post(NOTIFICATION_PATH, json=signed_notification(last_order(provider)))
    assert (response.status_code, response.text) == (200, "OK")
    assert client.get(f"/api/bookings/{booking['id']}").json()["status"] == "paid"


def test_a_forged_notification_is_rejected_without_touching_the_order(
    client: TestClient, provider: FakeProvider
) -> None:
    create(client)
    forged = signed_notification(last_order(provider))
    forged["order_status"] = "approved-by-someone"

    response = client.post(NOTIFICATION_PATH, json=forged)
    assert response.status_code == 400
    assert provider.report_calls == 0


def test_a_signed_notification_for_a_stranger_order_is_acknowledged(client: TestClient) -> None:
    response = client.post(NOTIFICATION_PATH, json=signed_notification("not-ours"))
    assert response.status_code == 200


def test_when_the_order_cannot_be_read_flitt_is_told_to_retry(
    client: TestClient, provider: FakeProvider
) -> None:
    create(client)
    provider.report_error = PaymentProviderError("down")
    response = client.post(NOTIFICATION_PATH, json=signed_notification(last_order(provider)))
    assert response.status_code >= 500, "a 2xx would make Flitt stop retrying a real payment"


def test_the_return_url_handed_to_the_provider_leads_back_to_the_booking_page(
    client: TestClient, provider: FakeProvider
) -> None:
    booking = create(client)
    handed_out = urlsplit(provider.checkout_requests[-1].return_url)

    # Flitt brings the customer back with a form POST carrying the order fields.
    response = client.post(
        f"{handed_out.path}?{handed_out.query}",
        data={"order_status": "approved", "signature": "whatever"},
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"https://ritis.dev/booking/?id={booking['id']}"
    assert provider.report_calls == 0, "the page asks the API; the return itself does not wait"


def test_the_notification_url_handed_to_the_provider_reaches_the_handler(
    client: TestClient, provider: FakeProvider
) -> None:
    booking = create(client)
    provider.approve(last_order(provider))
    handed_out = urlsplit(provider.checkout_requests[-1].notification_url)

    response = client.post(handed_out.path, json=signed_notification(last_order(provider)))
    assert (response.status_code, response.text) == (200, "OK")
    assert client.get(f"/api/bookings/{booking['id']}").json()["status"] == "paid"


@pytest.mark.parametrize(
    ("language", "page"),
    [("ru", "/booking/"), ("ka", "/ka/booking/"), ("en", "/en/booking/")],
)
def test_the_customer_comes_back_to_the_booking_page_in_their_language(
    client: TestClient, provider: FakeProvider, language: str, page: str
) -> None:
    response = client.post("/api/bookings", json={**FORM, "language": language}, headers=KEY)
    booking_id = response.json()["id"]
    handed_out = urlsplit(provider.checkout_requests[-1].return_url)

    back = client.post(f"{handed_out.path}?{handed_out.query}", data={"order_status": "approved"})

    assert back.headers["location"] == f"https://ritis.dev{page}?id={booking_id}"


@pytest.mark.parametrize("lang", ["", "de", "..%2F..%2Fevil", "%2F%2Fevil.example"])
def test_an_unknown_language_comes_back_to_the_default_page(client: TestClient, lang: str) -> None:
    response = client.get(f"/api/payments/flitt/return?booking={'a' * 32}&lang={lang}")

    assert response.headers["location"] == f"https://ritis.dev/booking/?id={'a' * 32}"


@pytest.mark.parametrize("query", ["", "?booking=../../etc", "?booking=ABC"])
def test_a_return_without_a_valid_booking_id(client: TestClient, query: str) -> None:
    response = client.get(f"/api/payments/flitt/return{query}")
    assert response.status_code == 303
    assert response.headers["location"] == "https://ritis.dev/booking/?error=not_found"
