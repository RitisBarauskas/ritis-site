"""Where Flitt calls us: server notifications and the customer's return from the checkout."""

from __future__ import annotations

import logging
import re
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Body, Query
from fastapi.responses import PlainTextResponse, RedirectResponse

from ritis_api.app.confirm_payment import ConfirmPayment, UnknownOrderError
from ritis_api.domain.identifiers import BookingId
from ritis_api.http.schemas import BOOKING_ID_PATTERN
from ritis_api.ports.payments import InvalidNotificationError, PaymentProvider
from ritis_api.ports.storage import BookingNotFoundError

log = logging.getLogger(__name__)


def flitt_router(
    provider: PaymentProvider, confirm_payment: ConfirmPayment, site_url: str
) -> APIRouter:
    router = APIRouter(prefix="/api/payments/flitt")
    booking_page = f"{site_url.rstrip('/')}/booking/"

    @router.post("/notification")
    def notification(payload: Annotated[dict[str, Any], Body()]) -> PlainTextResponse:
        try:
            order_id = provider.verify_notification(payload)
        except InvalidNotificationError as exc:
            log.warning("rejected Flitt notification: %s", exc)
            return PlainTextResponse("invalid notification", status_code=400)
        try:
            confirm_payment.confirm(order_id)
        except UnknownOrderError:
            # Signed but not ours: acknowledge, or Flitt keeps retrying for a day.
            log.warning("Flitt notification for unknown order %s", order_id)
        # Other failures answer 5xx on purpose: Flitt retries and the payment gets recorded.
        return PlainTextResponse("OK")

    # Flitt sends the customer back with a browser form POST carrying the order fields. They are
    # not trusted or read: the order is re-checked with the provider instead.
    @router.api_route("/return", methods=["GET", "POST"])
    def customer_return(booking: Annotated[str | None, Query()] = None) -> RedirectResponse:
        query = {"error": "not_found"}
        if booking is not None and re.fullmatch(BOOKING_ID_PATTERN, booking):
            try:
                confirm_payment.refresh(BookingId(booking))
                query = {"id": booking}
            except BookingNotFoundError:
                pass
        return RedirectResponse(f"{booking_page}?{urlencode(query)}", status_code=303)

    return router
