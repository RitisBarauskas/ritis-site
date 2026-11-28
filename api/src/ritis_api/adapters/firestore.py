"""BookingRepository on Firestore.

A booking is one document in `bookings/{id}`: the whole aggregate, its attempts included.
Firestore has no unique index, so each idempotency key owns a document of its own in
`idempotency_keys/{sha256 of the key}`, created in the same transaction as the booking.

Field `expire_at` is what the TTL policy on both collections (infra/) deletes by: set while
nobody has paid, so unpaid forms leave after the retention the privacy policy states.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import Any

from google.api_core.exceptions import Aborted
from google.cloud import firestore

from ritis_api.domain.booking import (
    UNPAID_RETENTION,
    Booking,
    BookingFormat,
    BookingStatus,
    Customer,
    Language,
    NoticeKind,
    OwnerNotice,
)
from ritis_api.domain.identifiers import BookingId, OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.domain.payment import AttemptStatus, PaymentAttempt
from ritis_api.ports.storage import (
    BookingNotFoundError,
    ConcurrentModificationError,
    DuplicateIdempotencyKeyError,
)

BOOKINGS = "bookings"
IDEMPOTENCY_KEYS = "idempotency_keys"


class FirestoreBookingRepository:
    # Rounds of the client's own retries a contended creation gets before it gives up.
    _CREATE_ROUNDS = 3

    def __init__(self, client: firestore.Client) -> None:
        self._client = client
        self._bookings = client.collection(BOOKINGS)
        self._keys = client.collection(IDEMPOTENCY_KEYS)

    def add(self, booking: Booking) -> None:
        booking_ref = self._bookings.document(booking.id)
        key_ref = self._keys.document(_key_id(booking.idempotency_key))

        @firestore.transactional
        def create(transaction: firestore.Transaction) -> None:
            # A read inside the transaction: a concurrent twin makes one of the two retry and
            # find the key taken, rather than both writing.
            if key_ref.get(transaction=transaction).exists:
                raise DuplicateIdempotencyKeyError(booking.idempotency_key)
            if booking_ref.get(transaction=transaction).exists:
                raise ValueError(f"booking {booking.id} already exists")
            # A repeat of a request finds its booking by the key for as long as an unpaid
            # booking is kept; a paid one is never repeated, the page holds the key.
            transaction.create(
                key_ref,
                {"booking_id": booking.id, "expire_at": booking.created_at + UNPAID_RETENTION},
            )
            transaction.create(booking_ref, _encode(booking, version=1))

        for _ in range(self._CREATE_ROUNDS):
            try:
                create(self._client.transaction())
            except ValueError as exc:
                if not _gave_up_on_contention(exc):
                    raise
                # A twin that won has its key stored; without one, nobody won yet: try again.
                if key_ref.get().exists:
                    raise DuplicateIdempotencyKeyError(booking.idempotency_key) from exc
                continue
            booking.version = 1
            return
        raise ConcurrentModificationError(booking.id)

    def get(self, booking_id: BookingId) -> Booking:
        snapshot = self._bookings.document(booking_id).get()
        if not snapshot.exists:
            raise BookingNotFoundError(booking_id)
        return _decode(booking_id, _data(snapshot))

    def find_by_idempotency_key(self, key: str) -> Booking | None:
        snapshot = self._keys.document(_key_id(key)).get()
        if not snapshot.exists:
            return None
        try:
            return self.get(BookingId(_data(snapshot)["booking_id"]))
        except BookingNotFoundError:
            # The booking was deleted by its retention before its key: the key is free again.
            return None

    def find_by_order_id(self, order_id: OrderId) -> Booking | None:
        query = self._bookings.where(
            filter=firestore.FieldFilter("order_ids", "array_contains", order_id)
        ).limit(1)
        for snapshot in query.stream():
            return _decode(BookingId(snapshot.id), _data(snapshot))
        return None

    def with_unsent_notices(self, limit: int) -> list[Booking]:
        query = self._bookings.where(
            filter=firestore.FieldFilter("has_unsent_notices", "==", True)
        ).limit(limit)
        return [_decode(BookingId(s.id), _data(s)) for s in query.stream()]

    def save(self, booking: Booking) -> None:
        booking_ref = self._bookings.document(booking.id)

        @firestore.transactional
        def write(transaction: firestore.Transaction) -> None:
            stored = booking_ref.get(transaction=transaction)
            if not stored.exists:
                raise BookingNotFoundError(booking.id)
            if _data(stored)["version"] != booking.version:
                raise ConcurrentModificationError(booking.id)
            transaction.set(booking_ref, _encode(booking, version=booking.version + 1))

        try:
            write(self._client.transaction())
        except ValueError as exc:
            if not _gave_up_on_contention(exc):
                raise
            raise ConcurrentModificationError(booking.id) from exc
        booking.version += 1


def _gave_up_on_contention(exc: ValueError) -> bool:
    # The client retries a transaction others keep aborting, then gives up with a ValueError
    # caused by the last Aborted (seen on the emulator: of 12 writers to one document, 1 wins).
    return isinstance(exc.__cause__, Aborted)


def _key_id(key: str) -> str:
    # A document id cannot hold every string ("/", "..", "__x__"); a digest always fits.
    return hashlib.sha256(key.encode()).hexdigest()


def _data(snapshot: Any) -> dict[str, Any]:
    data = snapshot.to_dict()
    if data is None:
        raise BookingNotFoundError(snapshot.id)
    return dict(data)


# --- encoding: one function per stored shape, and its exact inverse ----------------------


def _encode(booking: Booking, *, version: int) -> dict[str, Any]:
    return {
        "idempotency_key": booking.idempotency_key,
        "format": booking.format.value,
        "customer": {
            "name": booking.customer.name,
            "contact": booking.customer.contact,
            "about": booking.customer.about,
            "links": booking.customer.links,
        },
        "price": _encode_money(booking.price),
        "created_at": booking.created_at,
        "offer_revision": booking.offer_revision.isoformat(),
        "language": booking.language.value,
        "status": booking.status.value,
        "attempts": [_encode_attempt(a) for a in booking.attempts],
        # For find_by_order_id: Firestore indexes each element of an array for array_contains.
        "order_ids": [a.order_id for a in booking.attempts],
        "paid_at": booking.paid_at,
        "review_reason": booking.review_reason,
        "unsent_notices": [_encode_notice(n) for n in booking.unsent_notices],
        # For with_unsent_notices: an equality filter on a scalar needs no composite index.
        "has_unsent_notices": bool(booking.unsent_notices),
        "version": version,
        "expire_at": booking.discard_after,
    }


def _decode(booking_id: BookingId, data: dict[str, Any]) -> Booking:
    customer = data["customer"]
    return Booking(
        id=booking_id,
        idempotency_key=data["idempotency_key"],
        format=BookingFormat(data["format"]),
        customer=Customer(
            name=customer["name"],
            contact=customer["contact"],
            about=customer["about"],
            links=customer["links"],
        ),
        price=_decode_money(data["price"]),
        created_at=_utc(data["created_at"]),
        offer_revision=date.fromisoformat(data["offer_revision"]),
        language=Language(data["language"]),
        status=BookingStatus(data["status"]),
        attempts=[_decode_attempt(a) for a in data["attempts"]],
        paid_at=_utc_or_none(data["paid_at"]),
        review_reason=data["review_reason"],
        unsent_notices=[_decode_notice(n) for n in data["unsent_notices"]],
        version=data["version"],
    )


def _encode_notice(notice: OwnerNotice) -> dict[str, Any]:
    return {"kind": notice.kind.value, "at": notice.at, "reason": notice.reason}


def _decode_notice(data: dict[str, Any]) -> OwnerNotice:
    return OwnerNotice(NoticeKind(data["kind"]), _utc(data["at"]), data["reason"])


def _encode_attempt(attempt: PaymentAttempt) -> dict[str, Any]:
    return {
        "order_id": attempt.order_id,
        "provider": attempt.provider,
        "price": _encode_money(attempt.price),
        "created_at": attempt.created_at,
        "status": attempt.status.value,
        "charged": _encode_money_or_none(attempt.charged),
        "refunded": _encode_money_or_none(attempt.refunded),
        "checkout_url": attempt.checkout_url,
        "provider_payment_id": attempt.provider_payment_id,
    }


def _decode_attempt(data: dict[str, Any]) -> PaymentAttempt:
    return PaymentAttempt(
        order_id=OrderId(data["order_id"]),
        provider=data["provider"],
        price=_decode_money(data["price"]),
        created_at=_utc(data["created_at"]),
        status=AttemptStatus(data["status"]),
        charged=_decode_money_or_none(data["charged"]),
        refunded=_decode_money_or_none(data["refunded"]),
        checkout_url=data["checkout_url"],
        provider_payment_id=data["provider_payment_id"],
    )


def _encode_money(money: Money) -> dict[str, Any]:
    return {"amount_minor": money.amount_minor, "currency": money.currency.value}


def _decode_money(data: dict[str, Any]) -> Money:
    return Money(data["amount_minor"], Currency(data["currency"]))


def _encode_money_or_none(money: Money | None) -> dict[str, Any] | None:
    return None if money is None else _encode_money(money)


def _decode_money_or_none(data: dict[str, Any] | None) -> Money | None:
    return None if data is None else _decode_money(data)


def _utc(value: datetime) -> datetime:
    # Firestore returns its own datetime subclass; the domain gets a plain aware datetime.
    if value.tzinfo is None:
        raise ValueError("a stored timestamp without a time zone")
    utc = value.astimezone(UTC)
    return datetime(
        utc.year, utc.month, utc.day, utc.hour, utc.minute, utc.second, utc.microsecond, tzinfo=UTC
    )


def _utc_or_none(value: datetime | None) -> datetime | None:
    return None if value is None else _utc(value)
