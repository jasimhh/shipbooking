#!/usr/bin/env bash
# Nightly database backup. Run from cron/systemd as the app user:  deploy/backup.sh /srv/ship-booking/backups
# Postgres (DATABASE_URL set): custom-format pg_dump. SQLite: online copy. Keeps 14 days.
# Set BACKUP_GPG_RECIPIENT to encrypt each file for that key before it is stored.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
dest="${1:?usage: backup.sh <backup-dir>}"
mkdir -p "$dest"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"

if [ -n "${DATABASE_URL:-}" ]; then
  file="$dest/ship-booking-$stamp.dump"
  pg_dump --format=custom --no-owner --file="$file" "$DATABASE_URL"
else
  file="$dest/ship-booking-$stamp.sqlite3"
  "${PYTHON:-python3}" -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" \
    "${SQLITE_PATH:-db.sqlite3}" "$file"
fi

if [ -n "${BACKUP_GPG_RECIPIENT:-}" ]; then
  gpg --batch --yes --encrypt --recipient "$BACKUP_GPG_RECIPIENT" --output "$file.gpg" "$file" && rm "$file"
  file="$file.gpg"
fi
find "$dest" -name 'ship-booking-*' -mtime +14 -delete
echo "backup written: $file"
