# Recorded Flitt replies

Real replies from Flitt's public test merchant (`1549901`, key `test`, https://docs.flitt.com/api/testing/), recorded on 26.11.2026 for one order paid with test card `4444 5555 6666 1111` and then refunded by 50.00 and by the remaining 150.00 EUR.

- `checkout_url`, `checkout_bad_signature`, `status_not_found`, `reverse_partial`: as recorded. `reverse_partial` keeps Flitt's own signature and is what the signer is checked against.
- `status_*`: the payer's IP address in `additional_info` is replaced with `192.0.2.1` (RFC 5737), so these were re-signed with the public test key. Their signatures prove only that our signer agrees with itself; what they pin is Flitt's field set and values.
- That Flitt's own signature on a status reply passes our check is shown by `tests/live` for an unpaid order. For this paid order it was checked by hand on 27.11.2026 against the unpublished originals (approved, partially refunded, reversed): all three verified.
- `status_declined`: another order, opened with `delayed=N` and paid with the declining test card `4444 1111 5555 6666` on 27.11.2026; Flitt returned the customer at once and the order stayed declined. Its payer IP was replaced the same way; Flitt's own signature was verified before that.
- `response_signature_string` (a debug field of test mode) is removed everywhere.
