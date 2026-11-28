"""Owner notices as Telegram messages from the site's bot.

The bot token is part of every request URL, so no URL may reach a log or an error: the
composition root silences httpx's request log, and failures here name the error type only.
Messages carry what the privacy policy lists for this channel: the booking number, the format,
the name and the contact, never the description of the task.
"""

from __future__ import annotations

import httpx

from ritis_api.domain.booking import Booking, NoticeKind, OwnerNotice
from ritis_api.ports.notifications import NotifierError

TELEGRAM_API = "https://api.telegram.org"
_MESSAGE_LIMIT = 4096  # Telegram's limit for one text message


class TelegramNotifier:
    def __init__(
        self, http: httpx.Client, *, token: str, chat_id: int, base_url: str = TELEGRAM_API
    ) -> None:
        self._http = http
        self._url = f"{base_url}/bot{token}/sendMessage"
        self._chat_id = chat_id

    def send(self, notice: OwnerNotice, booking: Booking) -> None:
        # Plain text, no parse mode: a customer's name cannot turn into markup or a link.
        payload = {
            "chat_id": self._chat_id,
            "text": message(notice, booking)[:_MESSAGE_LIMIT],
            "link_preview_options": {"is_disabled": True},
        }
        try:
            response = self._http.post(self._url, json=payload)
        except httpx.HTTPError as exc:
            raise NotifierError(f"Telegram unreachable: {type(exc).__name__}") from None
        if response.status_code != httpx.codes.OK:
            raise NotifierError(f"Telegram answered {response.status_code}")


def message(notice: OwnerNotice, booking: Booking) -> str:
    match notice.kind:
        case NoticeKind.PAID:
            return (
                f"Оплачена бронь {booking.id}\n"
                f"{booking.format} · {booking.price} · сайт на {booking.language}\n"
                f"{booking.customer.name} — {booking.customer.contact}"
            )
        case NoticeKind.NEEDS_REVIEW:
            return f"Бронь {booking.id} ждёт проверки\n{notice.reason}"
