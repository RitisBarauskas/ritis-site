# Recorded Flitt replies

Real replies from Flitt's public test merchant (`1549901`, key `test`, https://docs.flitt.com/api/testing/), recorded on 26.11.2026 for one order paid with test card `4444 5555 6666 1111`, then refunded by 50.00 and by the remaining 150.00 EUR.

- `checkout_url`, `checkout_bad_signature`, `reverse_*`, `status_not_found`: recorded as is. `reverse_*` keep Flitt's own signature.
- `status_*`: the payer's IP address in `additional_info` is replaced with `192.0.2.1` (RFC 5737), so these were re-signed with the public test key. That Flitt's own status signatures pass our check is proven by `tests/live`.
- `response_signature_string` (a debug field of test mode) is removed everywhere.
