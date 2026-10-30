# Admin setup and day-to-day

## First run

1. `python manage.py createsuperuser` creates the first administrator.
2. Sign in at `/admin/`. Under **Accounts → Users**, give staff the right role:
   - **Administrator**: everything, including `/admin/` and money figures.
   - **Support staff**: support desk, passenger lists, cancellations to decide; no money figures; can check tickets but not mark boarding.
   - **Operator**: also needs an **Operator membership** (per-member "can edit schedules" and "can view manifests").
3. **Operators → Operators**: add each real operator and set verification to *Verified* only after checking their documents.
4. **Fleet**: ports (with latitude/longitude so they appear on the harbour map), routes, vessels and cabin classes. Ferries can also be added from the harbour map's **Add ferry** button.
5. **Schedules**: sailings and fares. Operator edits go to *Pending approval* for an admin to publish.
6. **Compliance → Policy versions**: publish approved policy texts. A published cancellation policy can carry refund bands (hours before departure → refund %). Until a policy is published its page shows the marked draft.
7. **Pages**: help guides, About, FAQs and service announcements.

## Daily

- **Harbour master** (`/staff/harbour/`): today's sailings, alerts (delays, cancellations, unpaid holds, complaints, cancellations to decide, refunds to send, privacy requests).
- **Bookings → Cancellation requests**: approve or reject; approval queues the refund.
- **Payments → Refunds**: send pending refunds; retry failed ones (a failed refund is retried in place, never re-queued).
- **Support desk** (`/staff/support/`): reply, assign, change status. Tickets marked "Sent without signing in" came from the contact form; the sender's identity isn't proven.
- **Compliance → Privacy requests**: answer access/correction requests; for deletion requests use the action **Delete (anonymise) the account**. It refuses while the person has upcoming trips.

## Cancelling a sailing

Set its status to *Cancelled* (admin action or edit). Every confirmed booking is cancelled, full refunds are queued and passengers are emailed. Set *Delayed* with a note to notify passengers of a delay.

## What is logged

Every admin create/edit/delete, role change, passenger-list view or download, report export, privacy export, anonymisation and boarding scan goes to **Compliance → Audit logs**, which cannot be edited or deleted.

## Things that need a developer

- Changing a person's email address (needs re-confirmation).
- Content pages accept HTML from admins and show it as-is: give the Pages permissions only to trusted administrators.
