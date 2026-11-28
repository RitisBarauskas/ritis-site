"""The composition root and its configuration, built for real (no network is touched)."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ritis_api.adapters.firestore import FirestoreBookingRepository
from ritis_api.adapters.flitt.signature import FlittSigner
from ritis_api.adapters.telegram import TelegramNotifier
from ritis_api.domain.booking import BookingStatus, NoticeKind, OwnerNotice
from ritis_api.http.flitt import NOTIFICATION_PATH, RETURN_PATH
from ritis_api.main import build_app
from ritis_api.settings import Settings
from tests.adapters.test_booking_repository import booking, emulated_firestore_project
from tests.fakes import NOW

SHARED_CATALOG = Path(__file__).resolve().parents[2] / "shared" / "catalog.json"


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "flitt_merchant_id": 1549901,
        "flitt_secret_key": "test",
        "api_base_url": "https://ritis.dev",
        "site_url": "https://ritis.dev/",
        "catalog_path": SHARED_CATALOG,
        **overrides,
    }
    # _env_file=None: a developer's api/.env must not leak into tests.
    return Settings(_env_file=None, **values)


def test_the_app_is_wired_end_to_end() -> None:
    with TestClient(build_app(settings()), follow_redirects=False) as client:
        assert client.get("/api/health").json() == {"status": "ok"}

        # Signed with the merchant's key: the check accepts it (an order we do not know is
        # acknowledged). A wrong key or merchant in the wiring would answer 400.
        notification = {"order_id": "not-ours", "merchant_id": 1549901, "order_status": "approved"}
        notification["signature"] = FlittSigner("test").sign(notification)
        assert client.post(NOTIFICATION_PATH, json=notification).status_code == 200
        assert client.post(NOTIFICATION_PATH, json={"order_id": "x"}).status_code == 400

        returned = client.get(f"{RETURN_PATH}?booking={'a' * 32}")
        assert returned.headers["location"] == f"https://ritis.dev/booking/?id={'a' * 32}"


@pytest.mark.parametrize(
    "url",
    ["", "ritis.dev", "http://ritis.dev", "javascript:alert(1)//", "https://ritis.dev/?x=1"],
)
def test_base_urls_must_be_https_without_a_query(url: str) -> None:
    with pytest.raises(ValidationError):
        settings(api_base_url=url)
    with pytest.raises(ValidationError):
        settings(site_url=url)


def test_plain_http_is_allowed_on_loopback_only() -> None:
    assert settings(api_base_url="http://127.0.0.1:8000/").api_base_url == "http://127.0.0.1:8000"
    assert settings(site_url="http://localhost:4321").site_url == "http://localhost:4321"


def test_a_misspelt_setting_is_an_error_not_ignored() -> None:
    with pytest.raises(ValidationError):
        settings(flitt_base_ur="https://pay.flitt.com")


def test_a_misspelt_environment_variable_stops_the_start(monkeypatch: pytest.MonkeyPatch) -> None:
    # In Cloud Run settings come from the environment, where unknown names are otherwise skipped.
    monkeypatch.setenv("RITIS_RECHEK_INTERVAL_SECONDS", "3")
    with pytest.raises(ValidationError, match="RITIS_RECHEK_INTERVAL_SECONDS"):
        settings()


def test_known_environment_variables_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RITIS_RECHECK_INTERVAL_SECONDS", "3")
    monkeypatch.setenv("PORT", "8080")
    assert settings().recheck_interval_seconds == 3


def test_a_missing_catalog_stops_the_start(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_app(settings(catalog_path=tmp_path / "missing.json"))


PRODUCTION = {
    "storage": "firestore",
    "telegram_bot_token": "123:token-of-the-bot",
    "telegram_chat_id": 42,
    "sweep_token": "s" * 40,
}


def test_memory_storage_is_refused_on_cloud_run(monkeypatch: pytest.MonkeyPatch) -> None:
    # Cloud Run sets K_SERVICE; its instances share no memory, so bookings would go missing.
    monkeypatch.setenv("K_SERVICE", "ritis-api")
    with pytest.raises(ValidationError, match="in-memory storage on Cloud Run"):
        settings(**{**PRODUCTION, "storage": "memory"})
    assert settings(**PRODUCTION).storage == "firestore"


@pytest.mark.parametrize("missing", ["telegram_bot_token", "sweep_token"])
def test_cloud_run_needs_telegram_and_the_sweep(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.setenv("K_SERVICE", "ritis-api")
    kept = {k: v for k, v in PRODUCTION.items() if k != missing}
    if missing == "telegram_bot_token":
        kept.pop("telegram_chat_id")
    with pytest.raises(ValidationError, match="Telegram"):
        settings(**kept)


def test_telegram_needs_both_the_token_and_the_chat() -> None:
    with pytest.raises(ValidationError, match="both"):
        settings(telegram_bot_token="123:token")


def test_the_bot_token_never_reaches_the_log(caplog: pytest.LogCaptureFixture) -> None:
    # httpx logs each request's URL at INFO, and the bot token is part of Telegram's URL.
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    build_app(settings(telegram_bot_token="123:secret-bot-token", telegram_chat_id=42))
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"ok": True}))
    notifier = TelegramNotifier(
        httpx.Client(transport=transport), token="123:secret-bot-token", chat_id=42
    )
    paid = booking()
    paid.unsent_notices = [OwnerNotice(NoticeKind.PAID, NOW)]

    with caplog.at_level(logging.DEBUG):
        notifier.send(paid.unsent_notices[0], paid)

    assert "secret-bot-token" not in caplog.text


@pytest.mark.firestore
def test_the_app_is_wired_to_firestore(monkeypatch: pytest.MonkeyPatch) -> None:
    project = f"demo-ritis-{uuid.uuid4().hex[:12]}"
    # A paid booking put straight into the emulator: only an app that reads Firestore finds it.
    seeded = booking()
    seeded.status = BookingStatus.PAID
    FirestoreBookingRepository(emulated_firestore_project(project)).add(seeded)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", project)

    with TestClient(build_app(settings(storage="firestore"))) as client:
        answer = client.get(f"/api/bookings/{seeded.id}")

    assert (answer.status_code, answer.json()["status"]) == (200, "paid")
