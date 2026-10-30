# Ship Booking

Ship and ferry booking platform prototype for India (INR). Django + DRF, Supabase Postgres (SQLite fallback for offline work), Razorpay in **test mode only**.

Status: **Phase 2 of 10** done: schema, design system and public pages (search, sailing details, help centre, FAQ, contact, service updates, policies). Booking and payment come in Phases 5 and 6.

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
