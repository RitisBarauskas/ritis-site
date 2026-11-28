# ritis-api

Backend of ritis.dev: paid bookings of the site's formats and their payments through [Flitt](https://docs.flitt.com/api/).

## Layout

Ports and adapters, with the rules in the domain:

- `domain/` — the `Booking` aggregate and its `PaymentAttempt`s, `Money`, and `PaymentReport` (what a provider says about an order: `NotCharged` or `Charged`). Pure Python: no HTTP, no SDKs, no storage.
- `app/` — use cases: `OpenBooking` (create a booking and open a checkout, idempotently) and `ConfirmPayment` (apply what the provider reports).
- `ports/` — what the use cases need from outside: `PaymentProvider`, `BookingRepository`, `Notifier`.
- `adapters/` — `flitt/` (signature, envelope client, provider, notification check), in-memory repository, log notifier.
- `http/` — FastAPI routes: bookings for the site, Flitt's notification and the customer's return.
- `main.py` — the composition root: the only place that knows the concrete adapters.

## How a payment is confirmed

1. `POST /api/bookings` with an `Idempotency-Key` creates the booking and opens a Flitt checkout. The price and the order text the customer sees at Flitt come from `shared/catalog.json` for the chosen format, never from the client; a package is booked at the price of the format it starts with. The booking keeps the site's language (`ru`, `ka` or `en`): the checkout page, the order text and the way back to the site's booking page follow it. Flitt shows an unknown language in English without an error, so the API accepts only these three. Reusing a key for different data, or in another language, is refused. A repeat with the same key answers with the same booking; if its checkout has outlived its lifetime, the order is re-read from Flitt first, so a dead checkout is never handed out.
2. One checkout is one try (`delayed=N`): after a decline the customer comes back and pays again through a new order.
3. Flitt notifies `POST /api/payments/flitt/notification`; the customer returns through `/api/payments/flitt/return` and is redirected to the booking page, which polls `GET /api/bookings/{id}`.
4. A notification is only a signal and the return is only navigation: the order is always re-read from Flitt with a signed request and applied to the booking. Repeats change nothing; polling reaches Flitt at most once per few seconds per order and per running instance.
5. Whatever the provider reports that contradicts the booking (another amount or currency, a second payment, a refund above the charge) is flagged for a human, never guessed or dropped. Refunds are made in Flitt's merchant portal and picked up the same way.
6. Every answer of the API carries `Cache-Control: no-store`: Firebase Hosting in front of it is a CDN, and a booking's state must never come from a cache.

## Locally

Needs [uv](https://docs.astral.sh/uv/) 0.11; it installs Python 3.13 itself.

```sh
cd api
cp .env.example .env        # Flitt's public test merchant
uv sync
uv run uvicorn ritis_api.main:build_app --factory --port 8000
```

Pay in Flitt's test checkout with card `4444 5555 6666 1111`, any expiry and CVV.

Bookings live in memory locally (`RITIS_STORAGE=memory`, the default); on Cloud Run they live in Firestore (`RITIS_STORAGE=firestore`), and the API refuses to start there with memory, which instances do not share.

Checks, the same as CI. The Firestore tests and the mutants need Google's Firestore emulator, here in Docker:

```sh
docker run -d --name ritis-firestore -p 127.0.0.1:8085:8085   gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators   gcloud emulators firestore start --host-port=0.0.0.0:8085
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8085

uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
uv run pytest -m firestore                 # the repository contract on the emulator
uv run python scripts/check_mutations.py   # every key rule, broken, must fail its own test
uv run pytest -m live                      # against Flitt's test merchant, over the network
```

## Owner notices

A payment, and each new flag for a human, is recorded by the booking itself as a notice, in the same write as the change; a notice leaves the booking only after the messenger took it, so it is delivered at least once and never lost. Delivery is tried right after the change; a Cloud Scheduler job calls `POST /api/internal/notices` with `Authorization: Bearer <RITIS_SWEEP_TOKEN>` every ten minutes to deliver what a down messenger left. A failing messenger, or a bug in it, never fails the request that recorded the money.

The messenger is Telegram (`RITIS_TELEGRAM_BOT_TOKEN`, `RITIS_TELEGRAM_CHAT_ID`); without them, locally, the log. A message carries the booking number, format, price, name and contact, as the privacy policy lists, never the description of the task. The bot token is part of Telegram's URL: httpx's request log is silenced and errors carry no URL. On Cloud Run the API refuses to start without Firestore, Telegram and the sweep token.

## Storage

A booking is one Firestore document in `bookings/{id}`, its payment attempts included; an idempotency key owns a document in `idempotency_keys/{sha256 of the key}`, created in the same transaction, since Firestore has no unique index. A save is a transaction that checks the version it read. A booking nobody paid for, and its key, carry `expire_at` (30 days after the booking, as the privacy policy states); Firestore's TTL policy on that field deletes them. A booking that took any money has no `expire_at` and stays.
