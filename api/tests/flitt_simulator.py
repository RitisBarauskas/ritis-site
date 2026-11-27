"""A stand-in for pay.flitt.com behind httpx.MockTransport.

Keeps orders, refuses requests with a wrong signature (error 1014) or a duplicate order id
(1013), answers status requests for unknown orders with 1018, and signs its status replies the
way Flitt does. Reply fields follow the replies recorded in adapters/flitt_replies/.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from ritis_api.adapters.flitt import FlittPaymentProvider
from ritis_api.adapters.flitt.signature import FlittSigner
from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Money

MERCHANT_ID = 1549901
SECRET = "test"


class FlittSimulator:
    def __init__(self) -> None:
        self._signer = FlittSigner(SECRET)
        self._orders: dict[str, dict[str, Any]] = {}
        self.requests: list[dict[str, Any]] = []

    def provider(self) -> FlittPaymentProvider:
        http = httpx.Client(transport=httpx.MockTransport(self._handle))
        return FlittPaymentProvider.connect(http, merchant_id=MERCHANT_ID, secret_key=SECRET)

    # --- what happens on Flitt's side ---------------------------------------------------------

    def approve(self, order_id: OrderId, charged: Money | None = None) -> None:
        order = self._orders[order_id]
        amount = charged.amount_minor if charged else order["amount"]
        currency = charged.currency.value if charged else order["currency"]
        order.update(order_status="approved", actual_amount=str(amount), actual_currency=currency)
        order["reversal_amount"] = "0"

    def decline(self, order_id: OrderId) -> None:
        self._orders[order_id]["order_status"] = "declined"

    def expire(self, order_id: OrderId) -> None:
        self._orders[order_id]["order_status"] = "expired"

    def refund(self, order_id: OrderId, amount: Money) -> None:
        order = self._orders[order_id]
        total = int(order["reversal_amount"]) + amount.amount_minor
        order["reversal_amount"] = str(total)
        if total == int(order["actual_amount"]):
            order["order_status"] = "reversed"

    # --- the API -------------------------------------------------------------------------------

    def _handle(self, request: httpx.Request) -> httpx.Response:
        fields = json.loads(request.content)["request"]
        self.requests.append(fields)
        if not self._signer.verify(fields):
            return self._failure(1014, "Invalid signature")
        if request.url.path == "/api/checkout/url":
            return self._create(fields)
        if request.url.path == "/api/status/order_id":
            return self._status(fields["order_id"])
        return httpx.Response(404)

    def _create(self, fields: dict[str, Any]) -> httpx.Response:
        order_id = fields["order_id"]
        if order_id in self._orders:
            return self._failure(1013, f"Duplicate order {order_id}")
        self._orders[order_id] = {
            "order_id": order_id,
            "merchant_id": MERCHANT_ID,
            "order_status": "created",
            "amount": fields["amount"],
            "currency": fields["currency"],
        }
        reply = {
            "checkout_url": f"https://pay.flitt.com/merchants/sim/index.html?token={order_id}",
            "payment_id": 1000000 + len(self._orders),
            "response_status": "success",
        }
        return httpx.Response(200, json={"response": reply})

    def _status(self, order_id: str) -> httpx.Response:
        if order_id not in self._orders:
            return self._failure(1018, f"Order {order_id} not found")
        reply = {**self._orders[order_id], "response_status": "success"}
        reply["signature"] = self._signer.sign(reply)
        return httpx.Response(200, json={"response": reply})

    @staticmethod
    def _failure(code: int, message: str) -> httpx.Response:
        reply = {"response_status": "failure", "error_code": code, "error_message": message}
        return httpx.Response(200, json={"response": reply})
