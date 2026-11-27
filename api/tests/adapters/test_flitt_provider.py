"""What is specific to Flitt: its request shape and its replies, recorded from its test merchant."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from ritis_api.adapters.flitt import FlittPaymentProvider
from ritis_api.adapters.flitt.signature import FlittSigner
from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.domain.payment import Charged, NotCharged, Outcome
from ritis_api.ports.payments import CheckoutRequest, OrderNotFoundError, PaymentProviderError

REPLIES = Path(__file__).with_name("flitt_replies")
SIGNER = FlittSigner("test")
EUR = Currency.EUR

Handler = Callable[[httpx.Request], httpx.Response]


def recorded(name: str) -> dict[str, Any]:
    reply: dict[str, Any] = json.loads((REPLIES / f"{name}.json").read_text(encoding="utf-8"))
    return reply


# The order every recorded status reply is about.
RECORDED_ORDER = OrderId(recorded("status_approved")["response"]["order_id"])


def provider_answering(handler: Handler) -> FlittPaymentProvider:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return FlittPaymentProvider.connect(http, merchant_id=1549901, secret_key="test")


def replying(body: dict[str, Any], seen: list[httpx.Request] | None = None) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=body)

    return handler


def signed_status(**fields: Any) -> dict[str, Any]:
    reply = {"order_id": RECORDED_ORDER, "response_status": "success", **fields}
    reply["signature"] = SIGNER.sign(reply)
    return {"response": reply}


def tampered_status() -> dict[str, Any]:
    reply = recorded("status_approved")
    reply["response"]["actual_amount"] = "1"
    return reply


def request_fields(request: httpx.Request) -> dict[str, Any]:
    envelope = json.loads(request.content)
    assert list(envelope) == ["request"], "Flitt expects the fields under one root 'request'"
    fields: dict[str, Any] = envelope["request"]
    return fields


def checkout_request(email: str | None = "client@example.com") -> CheckoutRequest:
    return CheckoutRequest(
        order_id=OrderId("order-1"),
        amount=Money(20000, EUR),
        description="ritis.dev — звонок 60 минут",
        return_url="https://ritis.dev/api/payments/flitt/return?booking=b1",
        notification_url="https://ritis.dev/api/payments/flitt/notification",
        lifetime_seconds=3600,
        language="ru",
        customer_email=email,
    )


class TestOpenCheckout:
    def test_a_signed_request_for_one_try_per_order(self) -> None:
        seen: list[httpx.Request] = []
        checkout = provider_answering(replying(recorded("checkout_url"), seen)).open_checkout(
            checkout_request()
        )

        recorded_reply = recorded("checkout_url")["response"]
        assert checkout.checkout_url == recorded_reply["checkout_url"]
        assert checkout.provider_payment_id == str(recorded_reply["payment_id"])
        (request,) = seen
        assert str(request.url) == "https://pay.flitt.com/api/checkout/url"
        fields = request_fields(request)
        assert SIGNER.verify(fields)
        assert {k: fields[k] for k in ("merchant_id", "order_id", "amount", "currency")} == {
            "merchant_id": 1549901,
            "order_id": "order-1",
            "amount": 20000,
            "currency": "EUR",
        }
        assert (fields["lang"], fields["lifetime"], fields["sender_email"]) == (
            "ru",
            3600,
            "client@example.com",
        )
        assert fields["server_callback_url"] == "https://ritis.dev/api/payments/flitt/notification"
        assert fields["response_url"] == "https://ritis.dev/api/payments/flitt/return?booking=b1"
        # Without it a declined customer may pay the same order later with another card.
        assert fields["delayed"] == "N"

    def test_absent_email_is_left_out_not_sent_as_null(self) -> None:
        seen: list[httpx.Request] = []
        provider_answering(replying(recorded("checkout_url"), seen)).open_checkout(
            checkout_request(email=None)
        )
        assert "sender_email" not in request_fields(seen[0])

    def test_a_refusal_names_flitts_error_code(self) -> None:
        provider = provider_answering(replying(recorded("checkout_bad_signature")))
        with pytest.raises(PaymentProviderError, match="error 1014"):
            provider.open_checkout(checkout_request())

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(502, text="Bad gateway"),
            httpx.Response(200, text="<html>maintenance</html>"),
            httpx.Response(200, json={"unexpected": True}),
            httpx.Response(200, json={"response": {"response_status": "success"}}),
            httpx.Response(
                200,
                json={
                    "response": {
                        "response_status": "success",
                        "checkout_url": "http://insecure.example",
                        "payment_id": 1,
                    }
                },
            ),
        ],
        ids=["http-502", "not-json", "no-envelope", "no-url", "plain-http-url"],
    )
    def test_unusable_replies_are_provider_errors(self, response: httpx.Response) -> None:
        with pytest.raises(PaymentProviderError):
            provider_answering(lambda _: response).open_checkout(checkout_request())

    def test_a_network_failure_is_a_provider_error(self) -> None:
        def unreachable(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timeout", request=request)

        with pytest.raises(PaymentProviderError):
            provider_answering(unreachable).open_checkout(checkout_request())


class TestReport:
    def test_recorded_paid_order(self) -> None:
        seen: list[httpx.Request] = []
        report = provider_answering(replying(recorded("status_approved"), seen)).report(
            RECORDED_ORDER
        )
        assert report == Charged(Money(20000, EUR), Money(0, EUR))
        assert str(seen[0].url) == "https://pay.flitt.com/api/status/order_id"
        assert SIGNER.verify(request_fields(seen[0]))

    def test_recorded_partial_and_full_refunds(self) -> None:
        partial = provider_answering(replying(recorded("status_partially_refunded")))
        assert partial.report(RECORDED_ORDER) == Charged(Money(20000, EUR), Money(5000, EUR))
        full = provider_answering(replying(recorded("status_reversed")))
        assert full.report(RECORDED_ORDER) == Charged(Money(20000, EUR), Money(20000, EUR))

    def test_recorded_declined_order_of_one_try_checkout(self) -> None:
        # Recorded after a declined card on an order opened with delayed=N.
        reply = recorded("status_declined")
        order_id = OrderId(reply["response"]["order_id"])
        assert provider_answering(replying(reply)).report(order_id) == NotCharged(Outcome.DECLINED)

    def test_the_charge_is_what_the_card_paid_not_what_was_asked(self) -> None:
        reply = signed_status(
            order_status="approved",
            amount="20000",
            currency="EUR",
            actual_amount="20100",
            actual_currency="USD",
            reversal_amount="0",
        )
        report = provider_answering(replying(reply)).report(RECORDED_ORDER)
        assert report == Charged(Money(20100, Currency.USD), Money(0, Currency.USD))

    def test_a_full_reversal_without_an_amount_refunds_the_whole_charge(self) -> None:
        reply = signed_status(order_status="reversed", actual_amount="20000", actual_currency="EUR")
        report = provider_answering(replying(reply)).report(RECORDED_ORDER)
        assert report == Charged(Money(20000, EUR), Money(20000, EUR))

    @pytest.mark.parametrize(
        ("flitt_status", "outcome"),
        [
            ("created", Outcome.PENDING),
            ("processing", Outcome.PENDING),
            ("declined", Outcome.DECLINED),
            ("expired", Outcome.EXPIRED),
        ],
    )
    def test_unpaid_states(self, flitt_status: str, outcome: Outcome) -> None:
        report = provider_answering(replying(signed_status(order_status=flitt_status))).report(
            RECORDED_ORDER
        )
        assert report == NotCharged(outcome)

    @pytest.mark.parametrize(
        "reply",
        [
            tampered_status(),
            signed_status(order_status="weird"),
            signed_status(order_status="approved", actual_currency="EUR"),
            signed_status(order_status="approved", actual_amount="1.5", actual_currency="EUR"),
            signed_status(order_status="approved", actual_amount="100", actual_currency="RUB"),
        ],
        ids=["tampered", "unknown-status", "no-amount", "fractional-amount", "foreign-currency"],
    )
    def test_unusable_status_replies(self, reply: dict[str, Any]) -> None:
        with pytest.raises(PaymentProviderError):
            provider_answering(replying(reply)).report(RECORDED_ORDER)

    def test_a_reply_about_another_order(self) -> None:
        with pytest.raises(PaymentProviderError, match="answered for order"):
            provider_answering(replying(recorded("status_approved"))).report(OrderId("other"))

    def test_recorded_unknown_order(self) -> None:
        with pytest.raises(OrderNotFoundError):
            provider_answering(replying(recorded("status_not_found"))).report(RECORDED_ORDER)
