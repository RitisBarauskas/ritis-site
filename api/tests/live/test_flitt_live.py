"""Against Flitt's public test merchant. Run explicitly: uv run pytest -m live

Proves what recorded replies cannot: Flitt accepts our signatures today, and its own
signatures on status replies pass our check.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from ritis_api.adapters.flitt import FlittPaymentProvider
from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.domain.payment import PaymentState
from ritis_api.ports.payments import CheckoutRequest, OrderNotFoundError

pytestmark = pytest.mark.live

# Published at https://docs.flitt.com/api/testing/
TEST_MERCHANT_ID = 1549901
TEST_SECRET = "test"


@pytest.fixture
def provider() -> FlittPaymentProvider:
    http = httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0))
    return FlittPaymentProvider.connect(http, merchant_id=TEST_MERCHANT_ID, secret_key=TEST_SECRET)


def test_open_checkout_then_read_its_signed_status(provider: FlittPaymentProvider) -> None:
    order_id = OrderId(f"ritis-live-{uuid.uuid4().hex}")
    checkout = provider.open_checkout(
        CheckoutRequest(
            order_id=order_id,
            amount=Money(100, Currency.EUR),
            description="ritis.dev live test",
            return_url="https://ritis.dev/api/payments/flitt/return?booking=live",
            notification_url="https://ritis.dev/api/payments/flitt/notification",
            lifetime_seconds=600,
            language="ru",
        )
    )
    assert checkout.checkout_url.startswith("https://pay.flitt.com/")
    assert provider.report(order_id).state is PaymentState.PENDING


def test_unknown_order(provider: FlittPaymentProvider) -> None:
    with pytest.raises(OrderNotFoundError):
        provider.report(OrderId(f"ritis-live-missing-{uuid.uuid4().hex}"))
