# Deploying Ship Booking

Target: one Linux server (Ubuntu 24.04 LTS or similar) running Nginx → Gunicorn → Django, with Postgres (Supabase or any managed Postgres). Files for every step are in [`deploy/`](../deploy).

Live payments stay **off** (`PAYMENTS_LIVE_MODE=false`) until everything in [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) is done.

## 1. Server

```bash
sudo apt update && sudo apt install -y python3-venv nginx postgresql-client certbot python3-certbot-nginx
sudo adduser --system --group --home /srv/ship-booking shipbooking
sudo -u shipbooking git clone <repo-url> /srv/ship-booking/app
sudo -u shipbooking python3 -m venv /srv/ship-booking/venv
sudo -u shipbooking /srv/ship-booking/venv/bin/pip install -r /srv/ship-booking/app/requirements.txt
```

## 2. Settings (`/srv/ship-booking/app/.env`)

Copy `.env.example` and set at least:

| Variable | Production value |
|---|---|
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | a new random value (`python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
| `DJANGO_ALLOWED_HOSTS` | `booking.example.in` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://booking.example.in` |
| `SITE_URL` | `https://booking.example.in` |
| `DATABASE_URL` | Postgres URL (Supabase: Session pooler, port 5432) |
| `TRUSTED_PROXY_HEADER` | `HTTP_X_REAL_IP` (matches the Nginx config) |
| `LOG_FORMAT` | `json` |
| `DJANGO_ADMINS` | who gets crash emails, e.g. `Ops <ops@example.in>` |
| `EMAIL_BACKEND` + SMTP settings | your email provider (see below) |
| `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL` | a verified sender address |
| `RAZORPAY_*` | **test** keys until launch; webhook secret from the Razorpay dashboard |
| `BUSINESS_*` | verified business facts only |

`chmod 600 .env` and keep it out of git. With `DJANGO_DEBUG=false` the app forces HTTPS, secure cookies, HSTS (30 days), a Content Security Policy and versioned static file names.

**Email:** set `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` plus `EMAIL_HOST`, `EMAIL_PORT=587`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS=true` for your provider (Amazon SES, Postmark, Zoho, etc.). Set up SPF and DKIM for the sending domain.

## 3. Database, static files, first admin

```bash
cd /srv/ship-booking/app
sudo -u shipbooking ../venv/bin/python manage.py migrate
sudo -u shipbooking ../venv/bin/python manage.py createcachetable      # shared rate-limit counters
sudo -u shipbooking ../venv/bin/python manage.py collectstatic --noinput
sudo -u shipbooking ../venv/bin/python manage.py createsuperuser
sudo -u shipbooking ../venv/bin/python manage.py check --deploy
```

Don't run `seed_demo` on a production database.

## 4. Gunicorn and scheduled jobs (systemd)

```bash
sudo cp deploy/systemd/* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ship-booking
sudo systemctl enable --now ship-booking-job@expire_holds.timer ship-booking-job@reconcile_payments.timer \
  ship-booking-job@apply_retention.timer ship-booking-job@clearsessions.timer
systemctl list-timers 'ship-booking*'
```

| Job | When | What |
|---|---|---|
| `expire_holds` | every minute | releases places held by unpaid reservations |
| `reconcile_payments` | every 5 minutes | settles payments Razorpay took but the site didn't hear about |
| `apply_retention` | daily 02:30 | removes personal data past its retention period |
| `clearsessions` | daily 03:00 | deletes expired sign-in sessions |

## 5. Nginx and HTTPS

```bash
sudo cp deploy/nginx/ship-booking.conf /etc/nginx/sites-available/ship-booking
sudo sed -i 's/booking.example.in/YOUR.DOMAIN/g' /etc/nginx/sites-available/ship-booking
sudo ln -s /etc/nginx/sites-available/ship-booking /etc/nginx/sites-enabled/
sudo certbot --nginx -d YOUR.DOMAIN
sudo nginx -t && sudo systemctl reload nginx
```

Then in the Razorpay dashboard add the webhook `https://YOUR.DOMAIN/payments/webhooks/razorpay/` for `payment.captured`, `payment.failed`, `order.paid`, `refund.processed` and `refund.failed`, with the same secret as `RAZORPAY_WEBHOOK_SECRET`.

## 6. Monitoring

- **Uptime:** point an uptime monitor (UptimeRobot, Better Stack, etc.) at `https://YOUR.DOMAIN/healthz`. It returns `200 {"status": "ok"}`, or `503` when the database is unreachable.
- **Errors:** crashes email a traceback to `DJANGO_ADMINS`.
- **Logs:** `journalctl -u ship-booking -f` (JSON lines when `LOG_FORMAT=json`; ship them to your log service). Job output: `journalctl -u 'ship-booking-job@*'`.
- **Payments:** check the admin's Payment transactions and Refunds lists daily; failed refunds also show on the harbour map alerts.

## 7. Backups

Supabase takes its own daily backups on paid plans. On top of that, keep your own:

```bash
# nightly, as shipbooking (cron or a systemd timer). Set BACKUP_GPG_RECIPIENT in .env to encrypt.
/srv/ship-booking/app/deploy/backup.sh /srv/ship-booking/backups
```

Copy backups off the server (object storage in a different region). **Test a restore every month** into a scratch database. Never point this at the live one:

```bash
RESTORE_DATABASE_URL=postgres://.../scratch deploy/restore-check.sh /srv/ship-booking/backups/ship-booking-<stamp>.dump
```

It restores the dump, runs Django's checks and migration check against it, and prints row counts.

## 8. Updating

```bash
cd /srv/ship-booking/app && sudo -u shipbooking git pull
sudo -u shipbooking ../venv/bin/pip install -r requirements.txt
sudo -u shipbooking ../venv/bin/python manage.py migrate
sudo -u shipbooking ../venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart ship-booking
```

Take a backup before any migration.

## Incident response (short version)

1. Check `/healthz`, `journalctl -u ship-booking`, and the Razorpay dashboard status.
2. If payments look wrong, stop taking new ones: set `RAZORPAY_KEY_ID=` (empty) and restart. Booking pages then say payments are unavailable. Run `reconcile_payments` once the cause is fixed.
3. For a suspected data breach: rotate `DJANGO_SECRET_KEY` (signs everyone out), the database password and the Razorpay keys. Keep logs, and follow CERT-In's reporting timelines (currently 6 hours for reportable incidents) with legal advice.
