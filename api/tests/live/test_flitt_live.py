"""Against Flitt's public test merchant. Run explicitly: uv run pytest -m live

Proves what recorded replies cannot: Flitt accepts our signatures today, and its own signature
on a status reply passes our check.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from ritis_api.adapters.flitt import FlittPaymentProvider
from ritis_api.domain.booking import Language
from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.domain.payment import NotCharged, Outcome
from ritis_api.ports.payments import CheckoutRequest, OrderNotFoundError

pytestmark = pytest.mark.live

# Published at https://docs.flitt.com/api/testing/
TEST_MERCHANT_ID = 1549901
TEST_SECRET = "test"


@pytest.fixture
def provider() -> FlittPaymentProvider:
    http = httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0))
    return FlittPaymentProvider.connect(http, merchant_id=TEST_MERCHANT_ID, secret_key=TEST_SECRET)


# Flitt accepts any lang and shows an unknown one in English: only a look at the page proves
# it speaks the language. Seen on 2026-11-27: ru, ka and en each render in their own language.
@pytest.mark.parametrize("language", list(Language))
def test_open_checkout_then_read_its_signed_status(
    provider: FlittPaymentProvider, language: Language
) -> None:
    order_id = OrderId(f"ritis-live-{uuid.uuid4().hex}")
    checkout = provider.open_checkout(
        CheckoutRequest(
            order_id=order_id,
            amount=Money(60000, Currency.GEL),
            description="ritis.dev live test",
            return_url="https://ritis.dev/api/payments/flitt/return?booking=live",
            notification_url="https://ritis.dev/api/payments/flitt/notification",
            lifetime_seconds=600,
            language=language.value,
        )
    )
    assert checkout.checkout_url.startswith("https://pay.flitt.com/")
    assert provider.report(order_id) == NotCharged(Outcome.PENDING)


def test_unknown_order(provider: FlittPaymentProvider) -> None:
    with pytest.raises(OrderNotFoundError):
        provider.report(OrderId(f"ritis-live-missing-{uuid.uuid4().hex}"))
