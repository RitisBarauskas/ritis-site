# ritis-api

Backend of ritis.dev: paid bookings of a call and their payments through [Flitt](https://docs.flitt.com/api/).

## Layout

Ports and adapters, with the rules in the domain:

- `domain/` — the `Booking` aggregate and its `PaymentAttempt`s, `Money`, `PaymentReport`. Pure Python: no HTTP, no SDKs, no storage.
- `app/` — use cases: `OpenBooking` (create and open a checkout), `ConfirmPayment` (apply what the provider reports), `RefundBooking`.
- `ports/` — what the use cases need from outside: `PaymentProvider`, `BookingRepository`, `Notifier`.
- `adapters/` — `flitt/` (signature, envelope client, provider), in-memory repository, log notifier.
- `http/` — FastAPI routes: bookings for the site, Flitt's notification and the customer's return.

## How a payment is confirmed

1. `POST /api/bookings` with an `Idempotency-Key` creates the booking and opens a Flitt checkout; the price comes from `shared/catalog.json`, never from the client.
2. Flitt notifies `POST /api/payments/flitt/notification` and sends the customer back to `/api/payments/flitt/return`, which redirects to the booking page.
3. Neither is trusted: both only trigger `ConfirmPayment`, which re-reads the order from Flitt with a signed request and applies it to the booking. Repeats change nothing.

## Locally

Needs [uv](https://docs.astral.sh/uv/); it installs Python 3.13 itself.

```sh
cd api
cp .env.example .env        # Flitt's public test merchant
uv sync
uv run uvicorn ritis_api.main:build_app --factory --port 8000
```

Checks, the same as CI:

```sh
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
uv run pytest -m live       # against Flitt's test merchant, over the network
```

Pay in Flitt's test checkout with card `4444 5555 6666 1111`, any expiry and CVV.
