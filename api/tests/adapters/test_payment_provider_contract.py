"""The PaymentProvider contract, held by the real Flitt adapter and by the test double alike.

Scenario tests run on FakeProvider; this suite is what makes their results mean something.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ritis_api.domain.identifiers import OrderId
from ritis_api.domain.money import Currency, Money
from ritis_api.domain.payment import Charged, NotCharged, Outcome
from ritis_api.ports.payments import (
    CheckoutRequest,
    OrderNotFoundError,
    PaymentProvider,
    PaymentProviderError,
)
from tests.fakes import FakeProvider
from tests.flitt_simulator import FlittSimulator

PRICE = Money(20000, Currency.EUR)
ORDER = OrderId("order-1")


@dataclass
class World:
    provider: PaymentProvider
    # The provider's side: what a customer and the provider's staff do to an order.
    side: FakeProvider | FlittSimulator


@pytest.fixture(params=["fake", "flitt"])
def world(request: pytest.FixtureRequest) -> World:
    if request.param == "fake":
        fake = FakeProvider()
        return World(fake, fake)
    simulator = FlittSimulator()
    return World(simulator.provider(), simulator)


def open_order(world: World, order_id: OrderId = ORDER) -> None:
    world.provider.open_checkout(
        CheckoutRequest(
            order_id=order_id,
            amount=PRICE,
            description="call",
            return_url="https://ritis.dev/return",
            notification_url="https://ritis.dev/notify",
            lifetime_seconds=3600,
            language="ru",
        )
    )


def test_a_new_checkout_is_pending(world: World) -> None:
    open_order(world)
    assert world.provider.report(ORDER) == NotCharged(Outcome.PENDING)


def test_an_approved_order_reports_its_charge(world: World) -> None:
    open_order(world)
    world.side.approve(ORDER)
    assert world.provider.report(ORDER) == Charged(PRICE, Money(0, Currency.EUR))


def test_a_charge_other_than_the_price_is_reported_as_charged(world: World) -> None:
    open_order(world)
    world.side.approve(ORDER, charged=Money(100, Currency.EUR))
    assert world.provider.report(ORDER) == Charged(Money(100, Currency.EUR), Money(0, Currency.EUR))


@pytest.mark.parametrize("outcome", [Outcome.DECLINED, Outcome.EXPIRED])
def test_failed_orders_are_not_charged(world: World, outcome: Outcome) -> None:
    open_order(world)
    if outcome is Outcome.DECLINED:
        world.side.decline(ORDER)
    else:
        world.side.expire(ORDER)
    assert world.provider.report(ORDER) == NotCharged(outcome)


def test_refunds_are_reported_as_a_running_total(world: World) -> None:
    open_order(world)
    world.side.approve(ORDER)
    world.side.refund(ORDER, Money(5000, Currency.EUR))
    assert world.provider.report(ORDER) == Charged(PRICE, Money(5000, Currency.EUR))
    world.side.refund(ORDER, Money(15000, Currency.EUR))
    assert world.provider.report(ORDER) == Charged(PRICE, PRICE)


def test_an_unknown_order(world: World) -> None:
    with pytest.raises(OrderNotFoundError):
        world.provider.report(OrderId("never-opened"))


def test_an_order_id_opens_one_checkout_only(world: World) -> None:
    open_order(world)
    with pytest.raises(PaymentProviderError):
        open_order(world)


def test_has_a_name_to_store_on_attempts(world: World) -> None:
    assert world.provider.name
