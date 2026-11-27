"""The composition root and its configuration, built for real (no network is touched)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ritis_api.adapters.flitt.signature import FlittSigner
from ritis_api.http.flitt import NOTIFICATION_PATH, RETURN_PATH
from ritis_api.main import build_app
from ritis_api.settings import Settings

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
