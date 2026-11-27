from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from ritis_api.adapters.flitt.signature import FlittSigner
from ritis_api.ports.payments import OrderNotFoundError, PaymentProviderError

BASE_URL = "https://pay.flitt.com"

# https://docs.flitt.com/api/response-codes/
_ERRORS_BY_CODE: dict[str, type[PaymentProviderError]] = {
    "1018": OrderNotFoundError,
}


class FlittClient:
    """Flitt's envelope: a signed {"request": …} goes out, a {"response": …} comes back.

    Turns transport failures, malformed replies and Flitt error codes into
    PaymentProviderError, and checks the signature of replies that carry one.
    """

    def __init__(
        self,
        http: httpx.Client,
        *,
        merchant_id: int,
        signer: FlittSigner,
        base_url: str = BASE_URL,
    ) -> None:
        self._http = http
        self._merchant_id = merchant_id
        self._signer = signer
        self._base_url = base_url.rstrip("/")

    @property
    def merchant_id(self) -> int:
        return self._merchant_id

    def call(
        self, path: str, fields: Mapping[str, object], *, signed_reply: bool
    ) -> dict[str, Any]:
        # Absent optional fields are left out rather than sent as null.
        request: dict[str, object] = {k: v for k, v in fields.items() if v is not None}
        request["merchant_id"] = self._merchant_id
        request["signature"] = self._signer.sign(request)
        reply = self._unwrap(path, self._post(path, request))
        if signed_reply and not self._signer.verify(reply):
            raise PaymentProviderError(f"Flitt {path}: reply signature does not match")
        return reply

    def _post(self, path: str, request: Mapping[str, object]) -> httpx.Response:
        try:
            response = self._http.post(f"{self._base_url}{path}", json={"request": request})
        except httpx.HTTPError as exc:
            raise PaymentProviderError(f"Flitt {path}: {type(exc).__name__}") from exc
        if response.status_code != httpx.codes.OK:
            raise PaymentProviderError(f"Flitt {path}: HTTP {response.status_code}")
        return response

    def _unwrap(self, path: str, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise PaymentProviderError(f"Flitt {path}: reply is not JSON") from exc
        reply = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(reply, dict):
            raise PaymentProviderError(f"Flitt {path}: reply has no 'response' object")
        if reply.get("response_status") != "success":
            code = reply.get("error_code")
            code = None if code in (None, "") else str(code)
            error = _ERRORS_BY_CODE.get(code or "", PaymentProviderError)
            raise error(f"Flitt {path}: {reply.get('error_message', 'request failed')}", code=code)
        return reply
