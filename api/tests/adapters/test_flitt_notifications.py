from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ritis_api.adapters.flitt import FlittNotifications, InvalidNotificationError
from ritis_api.adapters.flitt.signature import FlittSigner

SIGNER = FlittSigner("test")
NOTIFICATIONS = FlittNotifications(SIGNER, merchant_id=1549901)
# A notification carries the same fields as a status reply.
RECORDED = json.loads(
    (Path(__file__).with_name("flitt_replies") / "status_approved.json").read_text(encoding="utf-8")
)["response"]


def notification(**changes: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {**RECORDED, **changes}
    fields["signature"] = SIGNER.sign(fields)
    return fields


def test_a_signed_notification_names_its_order() -> None:
    assert NOTIFICATIONS.order_id_of(notification()) == RECORDED["order_id"]


def test_a_forged_field_breaks_the_signature() -> None:
    forged = notification()
    forged["order_status"] = "approved-by-someone"
    with pytest.raises(InvalidNotificationError, match="signature"):
        NOTIFICATIONS.order_id_of(forged)


def test_an_unsigned_notification() -> None:
    unsigned = notification()
    del unsigned["signature"]
    with pytest.raises(InvalidNotificationError, match="signature"):
        NOTIFICATIONS.order_id_of(unsigned)


def test_a_notification_for_another_merchant() -> None:
    with pytest.raises(InvalidNotificationError, match="another merchant"):
        NOTIFICATIONS.order_id_of(notification(merchant_id=1))


def test_a_notification_without_an_order() -> None:
    with pytest.raises(InvalidNotificationError, match="order_id"):
        NOTIFICATIONS.order_id_of(notification(order_id=""))
