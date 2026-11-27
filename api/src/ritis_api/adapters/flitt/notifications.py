from __future__ import annotations

from collections.abc import Mapping

from ritis_api.adapters.flitt.signature import FlittSigner
from ritis_api.domain.identifiers import OrderId


class InvalidNotificationError(Exception):
    """Not from Flitt, or not for this merchant."""


class FlittNotifications:
    """Flitt's server notifications (https://docs.flitt.com/api/callbacks/).

    A notification passing these checks is still only a signal: the order is then read from
    Flitt with a signed request, never taken from the notification body.
    """

    def __init__(self, signer: FlittSigner, *, merchant_id: int) -> None:
        self._signer = signer
        self._merchant_id = merchant_id

    @classmethod
    def for_merchant(cls, *, merchant_id: int, secret_key: str) -> FlittNotifications:
        return cls(FlittSigner(secret_key), merchant_id=merchant_id)

    def order_id_of(self, payload: Mapping[str, object]) -> OrderId:
        if not self._signer.verify(payload):
            raise InvalidNotificationError("signature does not match")
        if str(payload.get("merchant_id")) != str(self._merchant_id):
            raise InvalidNotificationError("notification for another merchant")
        order_id = payload.get("order_id")
        if not isinstance(order_id, str) or not order_id:
            raise InvalidNotificationError("notification without order_id")
        return OrderId(order_id)
