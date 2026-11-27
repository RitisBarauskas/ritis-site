from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from ritis_api.adapters.flitt.client import BASE_URL, FlittClient
from ritis_api.adapters.flitt.signature import FlittSigner
from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.domain.payment import Charged, NotCharged, Outcome, PaymentReport
from ritis_api.ports.payments import Checkout, CheckoutRequest, PaymentProviderError

# https://docs.flitt.com/api/order-parameters/
_NOT_CHARGED = {
    "created": Outcome.PENDING,
    "processing": Outcome.PENDING,
    "declined": Outcome.DECLINED,
    "expired": Outcome.EXPIRED,
}
_CHARGED = frozenset({"approved", "reversed"})


class FlittPaymentProvider:
    """PaymentProvider over Flitt's hosted checkout (https://docs.flitt.com/api/)."""

    name = "flitt"

    def __init__(self, client: FlittClient) -> None:
        self._client = client

    @classmethod
    def connect(
        cls, http: httpx.Client, *, merchant_id: int, secret_key: str, base_url: str = BASE_URL
    ) -> FlittPaymentProvider:
        signer = FlittSigner(secret_key)
        return cls(FlittClient(http, merchant_id=merchant_id, signer=signer, base_url=base_url))

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
            # One try per order (the port's contract). With the default "Y" a declined customer
            # stays on Flitt's page and may pay the same order with another card later.
            "delayed": "N",
        }
        # Flitt does not sign this reply; the URL only goes to the customer.
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


class _OrderReply:
    """Reads one Flitt order reply into a PaymentReport."""

    def __init__(self, reply: Mapping[str, Any], order_id: OrderId) -> None:
        if str(reply.get("order_id")) != order_id:
            raise PaymentProviderError(f"Flitt answered for order {reply.get('order_id')!r}")
        self._reply = reply

    def to_report(self) -> PaymentReport:
        status = str(self._reply.get("order_status"))
        if status in _NOT_CHARGED:
            return NotCharged(_NOT_CHARGED[status])
        if status not in _CHARGED:
            raise PaymentProviderError(f"unknown Flitt order_status {status!r}")
        # What the card was actually charged, which is what a human must reconcile.
        currency = self._currency()
        charged = Money(self._amount("actual_amount"), currency)
        reversal = self._reply.get("reversal_amount")
        if reversal in (None, ""):
            refunded = charged if status == "reversed" else Money.zero(currency)
        else:
            refunded = Money(self._amount("reversal_amount"), currency)
        return Charged(amount=charged, refunded=refunded)

    def _currency(self) -> Currency:
        raw = self._reply.get("actual_currency")
        try:
            return Currency(str(raw))
        except ValueError as exc:
            raise PaymentProviderError(f"unsupported Flitt actual_currency {raw!r}") from exc

    def _amount(self, field: str) -> int:
        # Flitt sends amounts in minor units, as integers or digit strings.
        raw = self._reply.get(field)
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.isdecimal():
            return int(raw)
        raise PaymentProviderError(f"bad Flitt amount in {field!r}: {raw!r}")
