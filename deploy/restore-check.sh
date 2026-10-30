#!/usr/bin/env bash
# Prove a backup restores: load it into a SCRATCH database and run the app's checks against it.
#   Postgres: RESTORE_DATABASE_URL=postgres://.../scratch deploy/restore-check.sh backups/ship-booking-....dump
#   SQLite:   deploy/restore-check.sh backups/ship-booking-....sqlite3
# Never point RESTORE_DATABASE_URL at the live database: pg_restore --clean drops tables first.
set -euo pipefail
cd "$(dirname "$0")/.."
file="${1:?usage: restore-check.sh <backup-file>}"
py="${PYTHON:-python3}"

if [[ "$file" == *.dump ]]; then
  : "${RESTORE_DATABASE_URL:?set RESTORE_DATABASE_URL to a scratch database}"
  pg_restore --clean --if-exists --no-owner --dbname="$RESTORE_DATABASE_URL" "$file"
  export DATABASE_URL="$RESTORE_DATABASE_URL"
else
  scratch="$(mktemp -d)/restore.sqlite3"
  cp "$file" "$scratch"
  export DATABASE_URL="" SQLITE_PATH="$scratch"
fi

"$py" manage.py check
"$py" manage.py migrate --check   # fails if the backup is missing migrations
"$py" manage.py shell -c "
from apps.bookings.models import Booking; from apps.accounts.models import User; from apps.compliance.models import AuditLog
print(f'restore OK: {User.objects.count()} users, {Booking.objects.count()} bookings, {AuditLog.objects.count()} audit entries')"
