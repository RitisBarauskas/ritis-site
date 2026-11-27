from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ritis_api.adapters.flitt.signature import FlittSigner

REPLIES = Path(__file__).with_name("flitt_replies")


def test_matches_the_documented_example() -> None:
    fields = {
        "server_callback_url": "http://myshop/callback/",
        "order_id": "TestOrder2",
        "currency": "GEL",
        "merchant_id": 1549901,
        "order_desc": "Test payment",
        "amount": 1000,
    }
    # Verbatim from https://docs.flitt.com/api/building-signature/
    documented = "test|1000|GEL|1549901|Test payment|TestOrder2|http://myshop/callback/"
    expected = hashlib.sha1(documented.encode()).hexdigest()  # noqa: S324
    assert FlittSigner("test").sign(fields) == expected


def test_empty_values_and_its_own_fields_are_not_signed() -> None:
    signer = FlittSigner("test")
    base = {"amount": 1000, "currency": "GEL"}
    noisy = {
        **base,
        "comment": "",
        "email": None,
        "signature": "x",
        "response_signature_string": "y",
    }
    assert signer.sign(noisy) == signer.sign(base)


def test_accepts_a_signature_made_by_flitt_itself() -> None:
    # Recorded as is: the signature was computed by Flitt, not by this code.
    reply = json.loads((REPLIES / "reverse_partial.json").read_text(encoding="utf-8"))["response"]
    assert FlittSigner("test").verify(reply)


@pytest.mark.parametrize(
    "tamper",
    [
        lambda r: r.update(reversal_amount="5001"),
        lambda r: r.update(signature=r["signature"].upper()),
        lambda r: r.pop("signature"),
        lambda r: r.update(signature=12345),
    ],
)
def test_rejects_tampered_or_missing_signatures(tamper: object) -> None:
    reply = json.loads((REPLIES / "reverse_partial.json").read_text(encoding="utf-8"))["response"]
    tamper(reply)  # type: ignore[operator]
    assert not FlittSigner("test").verify(reply)
    assert not FlittSigner("another-secret").verify(
        json.loads((REPLIES / "reverse_partial.json").read_text(encoding="utf-8"))["response"]
    )


def test_an_empty_secret_is_refused() -> None:
    with pytest.raises(ValueError, match="empty"):
        FlittSigner("")
