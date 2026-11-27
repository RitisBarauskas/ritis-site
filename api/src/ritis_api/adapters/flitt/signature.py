from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping

# Flitt never signs these two.
_UNSIGNED_FIELDS = frozenset({"signature", "response_signature_string"})


class FlittSigner:
    """Flitt's signature (https://docs.flitt.com/api/building-signature/).

    SHA1 of the secret key followed by the non-empty values sorted by field name, joined by "|".
    The same scheme covers our requests, Flitt's replies and its notifications.
    """

    def __init__(self, secret_key: str) -> None:
        if not secret_key:
            raise ValueError("Flitt secret key is empty")
        self._secret_key = secret_key

    def sign(self, fields: Mapping[str, object]) -> str:
        parts = [self._secret_key]
        for name in sorted(fields):
            value = fields[name]
            if name in _UNSIGNED_FIELDS or value is None or value == "":
                continue
            parts.append(str(value))
        # SHA1 is Flitt's scheme, not a choice we can make.
        return hashlib.sha1("|".join(parts).encode()).hexdigest()  # noqa: S324

    def verify(self, fields: Mapping[str, object]) -> bool:
        received = fields.get("signature")
        if not isinstance(received, str):
            return False
        return hmac.compare_digest(received.encode(), self.sign(fields).encode())
