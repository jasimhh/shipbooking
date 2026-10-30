# Ship Booking

Ship and ferry booking platform prototype for India (INR). Django + DRF, Supabase Postgres (SQLite fallback for offline work), Razorpay in **test mode only**.

Status: **Phase 8 of 10** done: everything up to the staff area (role-based dashboards, passenger lists, reports with CSV export, support desk) and passenger support conversations. Legal pages, cookie consent, accessibility and SEO come in Phase 9.

## Setup (Windows)

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env          # then set DJANGO_SECRET_KEY
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py seed_demo        # optional: demo sailings
.venv\Scripts\python manage.py createsuperuser
.venv\Scripts\python manage.py runserver
```

Site: http://127.0.0.1:8000/ · Admin: http://127.0.0.1:8000/admin/

`seed_demo` adds 14 days of sailings on Mumbai Ferry Wharf ↔ Mandwa Jetty and Phoenix Bay Jetty ↔ Swaraj Dweep (Havelock). The ports are real; the operator ("Demo Ferries (fictional)"), vessels, timings and fares are invented and labelled **Demo** everywhere on the site.

Help-centre guides, the About page, FAQs and service announcements are edited in the admin under **Pages**. Policy pages show the latest published **Policy version** and say "not published yet" until one exists.

## Accounts and roles

- Users sign in with email (case-insensitive). Five failed sign-ins from one IP for one email lock that pair out for 15 minutes.
- New accounts get a confirmation email (printed to the console in development). Booking will require a confirmed email.
- Roles: passenger, operator, support staff, administrator. Setting a user's role to administrator also gives them access to `/admin/`. Role and access changes made in the admin are written to the audit log.
- Operator staff are linked to operators through **Operator memberships**, with per-member "can edit schedules" and "can view manifests" switches. `apps/accounts/permissions.py` has the server-side checks every protected view must use: `role_required`, `operators_for`, `can_edit_schedules`, `can_view_manifest`.
- Not built: two-factor sign-in (optional in the spec) and changing your email address (needs re-confirmation; currently via support).

## Operations management

**Platform admins** use `/admin/`:
- Operators (verify or suspend with an action), their staff memberships, ports, routes, vessels with cabin classes and seats ("Create numbered seats" action for assigned-seating vessels), and sailings with their fares.
- Sailings go live with the **Approve and publish** action. A sailing can't be published without fares, after departure, or for an unverified operator; a live sailing saved without fares drops back to draft.
- Every create, edit and delete in these screens, including fare rows, is written to the audit log.

**Operator staff** use `/operator/` (same sign-in as the main site):
- They only ever see their own operator's vessels, routes and sailings. Vessels and routes are view-only.
- Staff with "can edit schedules" can create sailings and fares as drafts and submit them for approval. Only platform admins publish.
- On a live sailing they can only report a delay or cancellation and add a note; times, route and vessel are locked.
- Staff can't delete anything; cancel instead.

Rules checked on every save: route and vessel belong to the same operator; a vessel can't be on two sailings at overlapping times (cancelled ones don't count); arrival after departure; booking closes before departure; a fare's cabin class belongs to the sailing's vessel; fare capacity defaults to the cabin class, can't exceed it, and can't drop below places already held or sold.

Not built yet: creating repeating sailings in bulk (each sailing is added one at a time) and passenger lists (Phase 8, once bookings exist).

## Booking

1. On a sailing page, choose a class and number of passengers (1 to 9) and select **Book this sailing**. Booking needs a signed-in account with a confirmed email.
2. Enter each passenger's name, age and gender, plus a contact email and mobile number.
3. Review the price breakdown (fare, taxes, fees, total in INR) and the cancellation terms, then **Reserve places**.
4. The places are held for `INVENTORY_HOLD_MINUTES` (default 15) while the passenger pays. The booking page shows a live countdown and a **Cancel reservation** button.

How inventory stays correct (`apps/bookings/services.py`):
- Prices always come from the database; nothing the browser sends can change the total.
- Places are taken with a single conditional update that only succeeds while enough remain, inside a transaction, with the database's no-oversell constraint as a backstop.
- Ships with assigned seating get seats automatically, lowest number first; the database refuses to give one seat to two live bookings.
- Expired holds are released whenever someone searches, opens a sailing or a booking page, and by `python manage.py expire_holds`, which should run every minute from cron in production.
- Each account can have at most 3 unpaid reservations at a time, so nobody can tie up a sailing's places.
- Bookings are only visible to the account that made them.
- Demo sailings can't be booked if live payments are ever switched on.

Not built yet: choosing your own seat (seats are assigned automatically), guest checkout without an account, and booking look-up by reference for people without an account (Phase 7, with tickets).

## Payments (Razorpay, test mode)

### Setup
1. Create a Razorpay account and switch the dashboard to **Test Mode**.
2. **Account & Settings → API Keys → Generate Test Key.** Put the key id (`rzp_test_...`) and secret in `.env` as `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`.
3. **Account & Settings → Webhooks → Add New Webhook**: URL `https://<your-domain>/payments/webhooks/razorpay/`, choose a secret and put it in `.env` as `RAZORPAY_WEBHOOK_SECRET`, and select the events `payment.captured`, `payment.failed`, `payment.authorized` and `order.paid`. (Razorpay can't reach `localhost`; for local testing use a tunnel such as ngrok, or rely on the checkout return and `reconcile_payments`.)
4. Restart the server. Pay with Razorpay's test card or test UPI details from their documentation.

Leave `PAYMENTS_LIVE_MODE=false`. The app refuses to start with a live key while live mode is off, or a test key while it's on.

### How a payment is confirmed
- **Pay** creates a Razorpay order on the server for the booking's server-calculated total (in paise) and opens Razorpay Checkout. Reloading reuses the same order.
- When Checkout finishes, the browser posts the result back. The server checks Razorpay's signature, then fetches the payment from Razorpay's API and checks that the order, amount and currency match. Authorized payments are captured. Only then is the booking confirmed and its hold converted.
- **Webhooks** run the same confirmation, so a closed browser tab doesn't lose a payment. Every webhook must carry a valid signature; each event is stored once by its id, so repeats do nothing.
- `python manage.py reconcile_payments` (run every few minutes from cron) asks Razorpay about orders still waiting and settles any that were paid. Admins can also run **Check selected orders with Razorpay** on Payment transactions.
- If money arrives after the reservation was released, the booking is **not** confirmed and a full refund is queued for an admin (Payments → Refunds). Processing refunds through Razorpay comes in Phase 7.
- Failed payments are recorded; the passenger can try again with a fresh order while the places are still held.
- Only Razorpay ids and statuses are stored. Card numbers, CVVs, UPI PINs and bank passwords never reach this server.

## Tickets, cancellations and notifications

**E-tickets.** A ticket is issued the moment a payment is confirmed. Passengers download a PDF from their booking page. The QR code holds only a link with a random token (`/tickets/verify/<token>/`), never names or other personal data. Admins can **Reissue e-tickets** from Bookings; that voids the old QR code.

**Checking tickets at the port.** Scanning the QR code opens a check page for signed-in operator staff (with "can view manifests" for that operator), support staff and admins. It shows Valid, Already boarded or Not valid, lists the passengers, and has a **Mark as boarded** button. Every scan is logged. Passengers and other operators get "no access".

**Find a booking** (`/find-booking/`) lets anyone check a booking's status with its reference and the email it was booked with. It shows no passenger names and is limited to 10 look-ups an hour per network.

**Cancellations and refunds.**
- Refund amounts come only from the published cancellation policy. In the admin, open **Policy versions**, add the approved cancellation policy, and enter its refund bands (for example "24+ hours before departure: 75%"). The band with the most hours the passenger still meets applies. Nothing is hard-coded.
- Passengers request a cancellation from a confirmed booking before departure and see the refund they'd get first. With no published bands, an admin decides the amount.
- Admins **Approve** or **Reject** requests in Cancellation requests (and can adjust the amount before approving). Approving cancels the booking, releases its places and seats, voids its ticket and queues the refund.
- Admins send queued refunds with **Send selected refunds to Razorpay** in Refunds. A refund can never exceed what's left of the payment. Razorpay's `refund.processed` and `refund.failed` webhooks update the status; add those two events to the webhook.
- If an operator or admin **cancels a sailing**, every confirmed booking on it is cancelled and a full refund is queued automatically.

**Notifications.** Passengers are emailed when places are reserved, payment fails, a booking is confirmed (with the ticket link), a sailing is delayed or cancelled, and when a cancellation is requested, approved or rejected or a refund is sent or fails. Every email is stored under Support → Notifications with its status, is sent only after the change is saved, and appears under "Recent messages" on the account page. To change wording, add a Notification template with the same key (for example `booking_confirmed`). Set `SITE_URL` so links in emails and QR codes point to the real site. SMS isn't connected.

Not built yet: operator staff deciding cancellations (admins only for now), and choosing seats.

## Staff area (`/staff/`)

Operator staff, support staff and admins get a **Staff** button in the header. What each role sees:

| | Operator staff | Support staff | Admins |
|---|---|---|---|
| Dashboard: sailings in the next 7 days with occupancy, bookings, unpaid reservations | Own operators only | All | All |
| Money (payments received, refunds, net) | Own operators only | Hidden | All |
| Passenger lists per sailing (view, print, CSV) | Own operators, with "can view manifests" | Yes | Yes |
| Reports: bookings by status, cancellations, occupancy per sailing, CSV | Own operators only | Yes, without money | Yes |
| Support desk | No | Yes | Yes |
| Counts of cancellations to decide, refunds to send, sailings awaiting approval | No | Cancellations | All, with links into the admin |

- Every passenger-list view and download, and every report export, is written to the audit log. Lists contain only confirmed passengers.
- Reports default to the last 30 days of sales and the next 30 days of sailings. Operators can't widen a report to another operator, even by editing the address.

**Support desk** (`/staff/support/`): filter by status, topic or search; open a request to read the conversation, reply (the customer is emailed), change the status, or assign it to yourself. Complaints and grievances are highlighted. Every change is audited.

**Passengers** see their requests under Account → Support requests (`/account/support/`), read replies and answer back. Requests sent from the contact form before they registered appear once their email is confirmed.

**Harbour master** (`/staff/harbour/`): a live chart of today's sailings, one tab per area (state of the ports). Same role scoping as the dashboard.

- Ferry positions are **estimated** from the timetable and sailing status (boarding 30 minutes before, at sea between departure and arrival); there is no GPS feed. The page refreshes every 30 seconds.
- Side panel: today's numbers, alerts (delays, cancellations, unpaid holds about to lapse, unassigned complaints, cancellations and refunds waiting), sailings, passengers of the selected sailing (needs manifest access; each view is audited), and ferries.
- Admins can **Add ferry** with its cabin classes (`Deck · 120`, one per line). Add sailings for it in the admin as usual.
- Ports need latitude and longitude (admin → Ports) to be placed. Maharashtra and the Andaman Islands have drawn coastlines; other areas show ports on a plain grid.
- Weather and sea show "Not connected" until a marine weather service is added.
- Night/day theme toggle, remembered per browser.

## Tests

```bash
.venv\Scripts\python manage.py test apps
```

## Database: Supabase

1. Create a project at supabase.com.
2. Open **Connect** in the project, copy the **Direct connection** URI (IPv6) or the **Session pooler** URI (IPv4, port 5432) and put it in `.env` as `DATABASE_URL`. URL-encode special characters in the password. Don't use the transaction pooler (port 6543).
3. Run `.venv\Scripts\python manage.py migrate`.

Django owns the schema through its own migrations, so there are no Supabase SQL migrations. After every `migrate`, the app turns on RLS for every `public` table and revokes `anon`/`authenticated` access ([apps/compliance/apps.py](apps/compliance/apps.py)). The Supabase anon key can't read or write bookings through the Data API. Django connects as the table owner and isn't affected.

With `DATABASE_URL` empty the app uses a local SQLite file.

## Layout

| App | Holds |
|---|---|
| `accounts` | Email-login user with role (passenger/operator/support/admin), passenger profile |
| `operators` | Operators, operator memberships and per-member permissions |
| `fleet` | Ports, routes, vessels, cabin classes (capacity), seats (assigned seating only) |
| `schedules` | Sailings, fares + inventory counter, inventory holds |
| `bookings` | Bookings (server-side price snapshot), passengers, seat allocations, status history, cancellation requests |
| `payments` | Gateway transactions, webhook events (idempotent by event id), refunds |
| `tickets` | E-tickets (QR carries only a random token), verification events |
| `support` | Notifications, notification templates, support tickets and messages |
| `pages` | Public site: search, sailing pages, help guides, FAQs, announcements, contact form, policy pages |
| `compliance` | Append-only audit log, policy versions, cookie preferences, consent records, privacy requests |

## Rules the database enforces

- Origin and destination ports differ; arrival is after departure.
- Fares, taxes and fees are non-negative; passenger counts are positive.
- `Fare.units_allocated <= Fare.capacity`, so inventory can't be oversold.
- A seat can have only one active allocation per sailing.
- Booking, ticket and support references are unique.
- Webhook events are unique per gateway and event id.
- Audit log rows can't be edited or deleted through the ORM.

## Needed before production

These are left blank on purpose (`.env`, `BUSINESS_*`) and must come from the business, not be invented:

- Legal entity name, registered address, support email/phone, grievance officer
- Platform role: intermediary, marketplace or operator
- Real, authorised operators, vessels, ports, schedules and fares
- Approved cancellation/refund terms (percentages, deadlines, timelines)
- Razorpay account (test keys now, live keys only after the live-payment gate in the spec)
- Indian legal/compliance review (DPDP Act 2023, Consumer Protection E-Commerce Rules, IT Act, CERT-In, RBI)
