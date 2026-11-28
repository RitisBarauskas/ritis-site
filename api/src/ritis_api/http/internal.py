"""Routes for the platform, not for people: Cloud Scheduler's sweep of undelivered notices."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from ritis_api.app.deliver_notices import DeliverNotices

SWEEP_PATH = "/api/internal/notices"


def internal_router(deliver_notices: DeliverNotices, sweep_token: str | None) -> APIRouter:
    router = APIRouter()

    @router.post(SWEEP_PATH)
    def sweep(authorization: Annotated[str | None, Header()] = None) -> dict[str, int]:
        # No token configured (local runs): the route does not exist.
        if sweep_token is None:
            raise HTTPException(status_code=404)
        expected = f"Bearer {sweep_token}".encode()
        given = (authorization or "").encode()
        if not hmac.compare_digest(given, expected):
            raise HTTPException(status_code=401)
        return {"left": deliver_notices.sweep()}

    return router
