"""FlittPaymentProvider against replies recorded from Flitt (see flitt_replies/README.md)."""

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
from ritis_api.domain.payment import PaymentState
from ritis_api.ports.payments import (
    CheckoutRequest,
    InvalidNotificationError,
    OrderNotFoundError,
    PaymentProviderError,
    RefundStatus,
)

REPLIES = Path(__file__).with_name("flitt_replies")
MERCHANT_ID = 1549901
SIGNER = FlittSigner("test")

Handler = Callable[[httpx.Request], httpx.Response]


def recorded(name: str) -> dict[str, Any]:
    reply: dict[str, Any] = json.loads((REPLIES / f"{name}.json").read_text(encoding="utf-8"))
    return reply


# The order every recorded status and refund reply is about.
RECORDED_ORDER = OrderId(recorded("status_approved")["response"]["order_id"])


def provider_answering(handler: Handler) -> FlittPaymentProvider:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return FlittPaymentProvider.connect(http, merchant_id=MERCHANT_ID, secret_key="test")


def replying(body: dict[str, Any], seen: list[httpx.Request] | None = None) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=body)

    return handler


def request_fields(request: httpx.Request) -> dict[str, Any]:
    envelope = json.loads(request.content)
    assert list(envelope) == ["request"], "Flitt expects the fields under one root 'request'"
    fields: dict[str, Any] = envelope["request"]
    return fields


def checkout_request(email: str | None = "client@example.com") -> CheckoutRequest:
    return CheckoutRequest(
        order_id=OrderId("order-1"),
        amount=Money(20000, Currency.EUR),
        description="ritis.dev — звонок 60 минут",
        return_url="https://ritis.dev/api/payments/flitt/return?booking=b1",
        notification_url="https://ritis.dev/api/payments/flitt/notification",
        lifetime_seconds=3600,
        language="ru",
        customer_email=email,
    )


class TestOpenCheckout:
    def test_sends_a_signed_request_and_returns_the_checkout(self) -> None:
        seen: list[httpx.Request] = []
        checkout = provider_answering(replying(recorded("checkout_url"), seen)).open_checkout(
            checkout_request()
        )

        assert checkout.checkout_url == recorded("checkout_url")["response"]["checkout_url"]
        assert checkout.provider_payment_id == str(
            recorded("checkout_url")["response"]["payment_id"]
        )
        (request,) = seen
        assert str(request.url) == "https://pay.flitt.com/api/checkout/url"
        fields = request_fields(request)
        assert SIGNER.verify(fields)
        assert {
            k: fields[k] for k in ("merchant_id", "order_id", "amount", "currency", "lang")
        } == {
            "merchant_id": MERCHANT_ID,
            "order_id": "order-1",
            "amount": 20000,
            "currency": "EUR",
            "lang": "ru",
        }
        assert fields["server_callback_url"] == "https://ritis.dev/api/payments/flitt/notification"
        assert fields["response_url"] == "https://ritis.dev/api/payments/flitt/return?booking=b1"
        assert fields["sender_email"] == "client@example.com"

    def test_absent_email_is_not_sent_as_null(self) -> None:
        seen: list[httpx.Request] = []
        provider_answering(replying(recorded("checkout_url"), seen)).open_checkout(
            checkout_request(email=None)
        )
        assert "sender_email" not in request_fields(seen[0])

    def test_flitt_refusal_is_a_provider_error_with_its_code(self) -> None:
        provider = provider_answering(replying(recorded("checkout_bad_signature")))
        with pytest.raises(PaymentProviderError) as caught:
            provider.open_checkout(checkout_request())
        assert caught.value.code == "1014"

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
                        "checkout_url": "http://x",
                        "payment_id": 1,
                    }
                },
            ),
        ],
    )
    def test_unusable_replies_are_provider_errors(self, response: httpx.Response) -> None:
        with pytest.raises(PaymentProviderError):
            provider_answering(lambda _: response).open_checkout(checkout_request())

    def test_network_failure_is_a_provider_error(self) -> None:
        def unreachable(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timeout", request=request)

        with pytest.raises(PaymentProviderError):
            provider_answering(unreachable).open_checkout(checkout_request())


class TestReport:
    def test_paid_order(self) -> None:
        seen: list[httpx.Request] = []
        report = provider_answering(replying(recorded("status_approved"), seen)).report(
            RECORDED_ORDER
        )
        assert report.state is PaymentState.APPROVED
        assert report.charged == Money(20000, Currency.EUR)
        assert report.refunded == Money(0, Currency.EUR)
        assert str(seen[0].url) == "https://pay.flitt.com/api/status/order_id"
        assert SIGNER.verify(request_fields(seen[0]))

    def test_partially_refunded_order_reports_the_cumulative_refund(self) -> None:
        report = provider_answering(replying(recorded("status_partially_refunded"))).report(
            RECORDED_ORDER
        )
        assert report.state is PaymentState.APPROVED
        assert report.refunded == Money(5000, Currency.EUR)

    def test_fully_refunded_order(self) -> None:
        report = provider_answering(replying(recorded("status_reversed"))).report(RECORDED_ORDER)
        assert report.state is PaymentState.REVERSED
        assert report.refunded == Money(20000, Currency.EUR)

    @pytest.mark.parametrize(
        ("flitt_status", "state"),
        [
            ("created", PaymentState.PENDING),
            ("processing", PaymentState.PENDING),
            ("declined", PaymentState.DECLINED),
            ("expired", PaymentState.EXPIRED),
        ],
    )
    def test_unpaid_states(self, flitt_status: str, state: PaymentState) -> None:
        reply = {
            "order_id": RECORDED_ORDER,
            "order_status": flitt_status,
            "response_status": "success",
        }
        reply["signature"] = SIGNER.sign(reply)
        report = provider_answering(replying({"response": reply})).report(RECORDED_ORDER)
        assert report.state is state
        assert report.charged is None

    def test_a_tampered_reply_is_rejected(self) -> None:
        reply = recorded("status_approved")
        reply["response"]["actual_amount"] = "1"
        with pytest.raises(PaymentProviderError, match="signature"):
            provider_answering(replying(reply)).report(RECORDED_ORDER)

    def test_a_reply_about_another_order_is_rejected(self) -> None:
        with pytest.raises(PaymentProviderError, match="answered for order"):
            provider_answering(replying(recorded("status_approved"))).report(OrderId("other"))

    def test_an_unknown_status_is_rejected(self) -> None:
        reply = {"order_id": RECORDED_ORDER, "order_status": "weird", "response_status": "success"}
        reply["signature"] = SIGNER.sign(reply)
        with pytest.raises(PaymentProviderError, match="order_status"):
            provider_answering(replying({"response": reply})).report(RECORDED_ORDER)

    def test_unknown_order(self) -> None:
        with pytest.raises(OrderNotFoundError):
            provider_answering(replying(recorded("status_not_found"))).report(RECORDED_ORDER)


class TestRefund:
    def test_sends_the_amount_and_the_idempotency_key(self) -> None:
        seen: list[httpx.Request] = []
        status = provider_answering(replying(recorded("reverse_partial"), seen)).refund(
            RECORDED_ORDER, Money(5000, Currency.EUR), "refund-1"
        )
        assert status is RefundStatus.APPROVED
        fields = request_fields(seen[0])
        assert str(seen[0].url) == "https://pay.flitt.com/api/reverse/order_id"
        assert (fields["amount"], fields["currency"], fields["reverse_id"]) == (
            5000,
            "EUR",
            "refund-1",
        )
        assert SIGNER.verify(fields)

    @pytest.mark.parametrize(
        ("flitt_status", "status"),
        [("processing", RefundStatus.PENDING), ("declined", RefundStatus.DECLINED)],
    )
    def test_maps_refund_states(self, flitt_status: str, status: RefundStatus) -> None:
        reply = {
            "order_id": RECORDED_ORDER,
            "reverse_status": flitt_status,
            "response_status": "success",
        }
        reply["signature"] = SIGNER.sign(reply)
        provider = provider_answering(replying({"response": reply}))
        assert provider.refund(RECORDED_ORDER, Money(5000, Currency.EUR), "r") is status


class TestNotification:
    def notification(self, **changes: Any) -> dict[str, Any]:
        fields: dict[str, Any] = {**recorded("status_approved")["response"], **changes}
        fields["signature"] = SIGNER.sign(fields)
        return fields

    def test_returns_the_order_of_a_signed_notification(self) -> None:
        provider = provider_answering(lambda _: httpx.Response(500))
        assert provider.verify_notification(self.notification()) == RECORDED_ORDER

    def test_rejects_forgery_and_foreign_merchants(self) -> None:
        provider = provider_answering(lambda _: httpx.Response(500))
        forged = self.notification()
        forged["order_status"] = "approved-by-attacker"
        with pytest.raises(InvalidNotificationError, match="signature"):
            provider.verify_notification(forged)
        with pytest.raises(InvalidNotificationError, match="another merchant"):
            provider.verify_notification(self.notification(merchant_id=1))
        with pytest.raises(InvalidNotificationError, match="order_id"):
            provider.verify_notification(self.notification(order_id=""))
