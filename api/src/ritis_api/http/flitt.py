"""Where Flitt calls us: server notifications and the customer's return from the checkout."""

from __future__ import annotations

import logging
import re
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Body, Query
from fastapi.responses import PlainTextResponse, RedirectResponse

from ritis_api.adapters.flitt import FlittNotifications, InvalidNotificationError
from ritis_api.app.confirm_payment import ConfirmPayment, UnknownOrderError
from ritis_api.app.open_booking import CheckoutSettings
from ritis_api.http.schemas import BOOKING_ID_PATTERN

log = logging.getLogger(__name__)

NOTIFICATION_PATH = "/api/payments/flitt/notification"
RETURN_PATH = "/api/payments/flitt/return"


def flitt_checkout_settings(api_base_url: str, *, lifetime_seconds: int) -> CheckoutSettings:
    """The URLs Flitt is given, built from the very paths the routes below are served at."""
    return CheckoutSettings(
        return_url_template=f"{api_base_url}{RETURN_PATH}?booking={{booking_id}}",
        notification_url=f"{api_base_url}{NOTIFICATION_PATH}",
        lifetime_seconds=lifetime_seconds,
    )


def flitt_router(
    notifications: FlittNotifications, confirm_payment: ConfirmPayment, site_url: str
) -> APIRouter:
    router = APIRouter()
    booking_page = f"{site_url.rstrip('/')}/booking/"

    @router.post(NOTIFICATION_PATH)
    def notification(payload: Annotated[dict[str, Any], Body()]) -> PlainTextResponse:
        try:
            order_id = notifications.order_id_of(payload)
        except InvalidNotificationError as exc:
            log.warning("rejected Flitt notification: %s", exc)
            return PlainTextResponse("invalid notification", status_code=400)
        try:
            confirm_payment.confirm(order_id)
        except UnknownOrderError:
            # Signed but not ours: acknowledge, or Flitt keeps retrying for a day.
            log.warning("Flitt notification for unknown order %s", order_id)
        # Any other failure answers an error status on purpose: Flitt retries until it is recorded.
        return PlainTextResponse("OK")

    # Flitt sends the customer back with a browser form POST carrying the order fields. Nothing
    # in it is trusted or read, and nothing is checked here: the booking page asks the API.
    @router.api_route(RETURN_PATH, methods=["GET", "POST"])
    def customer_return(booking: Annotated[str | None, Query()] = None) -> RedirectResponse:
        valid = booking is not None and re.fullmatch(BOOKING_ID_PATTERN, booking)
        query = {"id": booking} if valid else {"error": "not_found"}
        return RedirectResponse(f"{booking_page}?{urlencode(query)}", status_code=303)

    return router
