"""The sweep Cloud Scheduler calls: only with its token, and it delivers what was left."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ritis_api.adapters.memory import InMemoryBookingRepository
from ritis_api.http.internal import SWEEP_PATH
from tests.fakes import FakeProvider, RecordingNotifier
from tests.http.conftest import SWEEP_TOKEN, create, last_order, signed_notification


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Bearer", f"Bearer {SWEEP_TOKEN}x", f"bearer {SWEEP_TOKEN}", SWEEP_TOKEN],
)
def test_the_sweep_needs_its_token(client: TestClient, authorization: str | None) -> None:
    headers = {} if authorization is None else {"Authorization": authorization}

    assert client.post(SWEEP_PATH, headers=headers).status_code == 401


def test_the_sweep_delivers_a_notice_the_messenger_refused_before(
    client: TestClient,
    provider: FakeProvider,
    notifier: RecordingNotifier,
    repository: InMemoryBookingRepository,
) -> None:
    booking = create(client)
    provider.approve(last_order(provider))
    notifier.broken = True
    client.post("/api/payments/flitt/notification", json=signed_notification(last_order(provider)))
    assert notifier.paid == []
    notifier.broken = False

    answer = client.post(SWEEP_PATH, headers={"Authorization": f"Bearer {SWEEP_TOKEN}"})

    assert answer.json() == {"left": 0}
    assert notifier.paid == [booking["id"]]
    assert repository.with_unsent_notices(limit=10) == []
