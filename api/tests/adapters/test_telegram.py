"""The Telegram notifier against a stand-in for the Bot API: what it sends and how it fails."""

from __future__ import annotations

import json

import httpx
import pytest

from ritis_api.adapters.telegram import TelegramNotifier
from ritis_api.domain.booking import Booking, NoticeKind, OwnerNotice
from ritis_api.domain.money import Currency, Money
from ritis_api.ports.notifications import NotifierError
from tests.adapters.test_booking_repository import booking
from tests.fakes import NOW

TOKEN = "123456:bot-token-that-must-stay-secret"
PAID = OwnerNotice(NoticeKind.PAID, NOW)


def notifier(handler: httpx.MockTransport) -> TelegramNotifier:
    return TelegramNotifier(httpx.Client(transport=handler), token=TOKEN, chat_id=42)


def customer_booking() -> Booking:
    b = booking()
    b.customer = type(b.customer)(
        name="Анна <b>", contact="@anna", about="secret plans of the startup", links="https://x"
    )
    b.price = Money(60000, Currency.GEL)
    return b


def test_sends_the_booking_to_the_owner_chat_as_plain_text() -> None:
    sent: list[httpx.Request] = []

    def bot_api(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    notifier(httpx.MockTransport(bot_api)).send(PAID, customer_booking())

    (request,) = sent
    assert str(request.url) == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    body = json.loads(request.content)
    assert body["chat_id"] == 42
    assert "parse_mode" not in body, "a customer's name must stay text, never markup"
    text = body["text"]
    for expected in ("a" * 32, "start", "600.00 GEL", "Анна <b>", "@anna", "ka"):
        assert expected in text
    # The privacy policy promises this channel only number, format, name and contact.
    assert "secret plans" not in text
    assert "https://x" not in text


def test_a_flag_carries_its_reason() -> None:
    texts: list[str] = []

    def bot_api(request: httpx.Request) -> httpx.Response:
        texts.append(json.loads(request.content)["text"])
        return httpx.Response(200, json={"ok": True})

    notice = OwnerNotice(NoticeKind.NEEDS_REVIEW, NOW, "charged 300.00 EUR, expected 200.00 EUR")
    notifier(httpx.MockTransport(bot_api)).send(notice, customer_booking())

    assert "charged 300.00 EUR, expected 200.00 EUR" in texts[0]


@pytest.mark.parametrize("status", [400, 401, 429, 500])
def test_a_refusal_is_a_notifier_error(status: int) -> None:
    bot_api = httpx.MockTransport(lambda _: httpx.Response(status, json={"ok": False}))

    with pytest.raises(NotifierError, match=str(status)):
        notifier(bot_api).send(PAID, customer_booking())


def test_an_unreachable_api_is_a_notifier_error_without_the_token() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    with pytest.raises(NotifierError) as caught:
        notifier(httpx.MockTransport(down)).send(PAID, customer_booking())

    # The connection error names the URL, and the URL holds the token: none of it may surface.
    assert TOKEN not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
