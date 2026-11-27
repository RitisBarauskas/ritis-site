from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from ritis_api.adapters.flitt.client import BASE_URL, FlittClient
from ritis_api.adapters.flitt.signature import FlittSigner
from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.domain.payment import PaymentReport, PaymentState
from ritis_api.ports.payments import (
    Checkout,
    CheckoutRequest,
    InvalidNotificationError,
    PaymentProviderError,
    RefundStatus,
)

# https://docs.flitt.com/api/order-parameters/
_ORDER_STATES = {
    "created": PaymentState.PENDING,
    "processing": PaymentState.PENDING,
    "approved": PaymentState.APPROVED,
    "declined": PaymentState.DECLINED,
    "expired": PaymentState.EXPIRED,
    "reversed": PaymentState.REVERSED,
}

# https://docs.flitt.com/api/reversal-parameters/
_REFUND_STATES = {
    "created": RefundStatus.PENDING,
    "processing": RefundStatus.PENDING,
    "approved": RefundStatus.APPROVED,
    "reversed": RefundStatus.APPROVED,
    "declined": RefundStatus.DECLINED,
    "expired": RefundStatus.DECLINED,
}


class FlittPaymentProvider:
    """PaymentProvider over Flitt's hosted checkout (https://docs.flitt.com/api/)."""

    def __init__(self, client: FlittClient, signer: FlittSigner) -> None:
        self._client = client
        self._signer = signer

    @classmethod
    def connect(
        cls, http: httpx.Client, *, merchant_id: int, secret_key: str, base_url: str = BASE_URL
    ) -> FlittPaymentProvider:
        signer = FlittSigner(secret_key)
        client = FlittClient(http, merchant_id=merchant_id, signer=signer, base_url=base_url)
        return cls(client, signer)

    def open_checkout(self, request: CheckoutRequest) -> Checkout:
        fields: dict[str, object] = {
            "order_id": request.order_id,
            "order_desc": request.description,
            "amount": request.amount.amount_minor,
            "currency": request.amount.currency.value,
            "response_url": request.return_url,
            "server_callback_url": request.notification_url,
            "lifetime": request.lifetime_seconds,
            "lang": request.language,
            "sender_email": request.customer_email,
        }
        # Flitt does not sign this reply; the checkout URL is only handed to the customer.
        reply = self._client.call("/api/checkout/url", fields, signed_reply=False)
        checkout_url = reply.get("checkout_url")
        payment_id = reply.get("payment_id")
        if not isinstance(checkout_url, str) or not checkout_url.startswith("https://"):
            raise PaymentProviderError(f"Flitt returned no usable checkout_url: {checkout_url!r}")
        if payment_id in (None, ""):
            raise PaymentProviderError("Flitt returned no payment_id")
        return Checkout(checkout_url=checkout_url, provider_payment_id=str(payment_id))

    def report(self, order_id: OrderId) -> PaymentReport:
        reply = self._client.call("/api/status/order_id", {"order_id": order_id}, signed_reply=True)
        return _OrderReply(reply, order_id).to_report()

    def refund(self, order_id: OrderId, amount: Money, refund_id: str) -> RefundStatus:
        fields = {
            "order_id": order_id,
            "amount": amount.amount_minor,
            "currency": amount.currency.value,
            "reverse_id": refund_id,
        }
        reply = self._client.call("/api/reverse/order_id", fields, signed_reply=True)
        raw = str(reply.get("reverse_status"))
        if raw not in _REFUND_STATES:
            raise PaymentProviderError(f"unknown Flitt reverse_status {raw!r}")
        return _REFUND_STATES[raw]

    def verify_notification(self, payload: Mapping[str, object]) -> OrderId:
        if not self._signer.verify(payload):
            raise InvalidNotificationError("signature does not match")
        if str(payload.get("merchant_id")) != str(self._client.merchant_id):
            raise InvalidNotificationError("notification for another merchant")
        order_id = payload.get("order_id")
        if not isinstance(order_id, str) or not order_id:
            raise InvalidNotificationError("notification without order_id")
        return OrderId(order_id)


class _OrderReply:
    """Reads one Flitt order reply into a PaymentReport."""

    def __init__(self, reply: Mapping[str, Any], order_id: OrderId) -> None:
        if str(reply.get("order_id")) != order_id:
            raise PaymentProviderError(f"Flitt answered for order {reply.get('order_id')!r}")
        self._reply = reply

    def to_report(self) -> PaymentReport:
        raw = str(self._reply.get("order_status"))
        if raw not in _ORDER_STATES:
            raise PaymentProviderError(f"unknown Flitt order_status {raw!r}")
        state = _ORDER_STATES[raw]
        if state not in {PaymentState.APPROVED, PaymentState.REVERSED}:
            return PaymentReport(state)
        currency = self._currency()
        return PaymentReport(
            state,
            charged=Money(self._amount("actual_amount", "amount"), currency),
            # Cumulative over all refunds of the order.
            refunded=Money(self._amount("reversal_amount", default=0), currency),
        )

    def _currency(self) -> Currency:
        raw = self._reply.get("actual_currency") or self._reply.get("currency")
        try:
            return Currency(str(raw))
        except ValueError as exc:
            raise PaymentProviderError(f"unsupported Flitt currency {raw!r}") from exc

    def _amount(
        self, field: str, fallback: str | None = None, *, default: int | None = None
    ) -> int:
        # Flitt sends amounts in minor units, as integers or digit strings.
        raw = self._reply.get(field)
        if raw in (None, "") and fallback is not None:
            raw = self._reply.get(fallback)
        if raw in (None, "") and default is not None:
            return default
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.isdecimal():
            return int(raw)
        raise PaymentProviderError(f"bad Flitt amount in {field!r}: {raw!r}")
