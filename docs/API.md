# HTTP endpoints for machines

Ship Booking is a server-rendered site; there is no public REST API. These are the endpoints meant for programs rather than people.

## Razorpay webhook

`POST /payments/webhooks/razorpay/`

| | |
|---|---|
| Called by | Razorpay |
| Auth | `X-Razorpay-Signature`: HMAC-SHA256 of the raw body with `RAZORPAY_WEBHOOK_SECRET`. Missing secret or bad signature → `400 invalid signature`. |
| Idempotency | `X-Razorpay-Event-Id` (or, if absent, a SHA-256 of the body). Each event is stored once (`GatewayEvent`, unique per gateway + event id); repeats return `200` without acting again. |
| Events handled | `payment.captured`, `order.paid`, `payment.authorized` (confirm the booking after re-checking amount and currency), `payment.failed`, `refund.processed`, `refund.failed`. Others are stored and ignored. |
| Response | `200` with a short outcome text, `400` for a bad signature or body. |

A payment that arrives after the reservation's hold expired is refunded automatically instead of confirming the booking.

## Health check

`GET /healthz` → `200 {"status": "ok"}` or `503 {"status": "database unavailable"}`. No auth; reveals nothing else. `Cache-Control: no-store`.

## Harbour master data (staff, signed in)

`GET /staff/harbour/sailings/<id>/passengers.json`

- Who: admins, support staff, and operator staff with "can view manifests" for that sailing's operator. Everyone else gets `403`.
- Returns `{"sailing": <id>, "passengers": [{"name", "initials", "booking", "age", "gender", "email", "phone", "cabin", "ticket", "state", "payment", "admin_url"}]}` for confirmed and pending bookings (`admin_url` is empty for non-admins).
- Every call is written to the audit log (`harbour.passengers_viewed`). `Cache-Control: private, no-store`.

The map page itself (`/staff/harbour/`) embeds its data with `json_script`; it is not a separate endpoint.

## Personal data export (signed in)

`GET /privacy/my-data.json` returns everything held about the signed-in person (account, bookings, passengers, payments, support messages, consent records) as a JSON download. Audited as `privacy.data_exported`.

## Ticket QR codes

The QR on each e-ticket encodes `SITE_URL/tickets/verify/<token>/`, where the token is 32 random URL-safe characters and carries no personal data. Opening it needs a signed-in admin, support or crew account; crew and admins mark boarding with `POST .../board/` (CSRF-protected).

## SEO files

`/robots.txt` and `/sitemap.xml` (public pages only).
