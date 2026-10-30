from django.apps import AppConfig
from django.db.models.signals import post_migrate

# Django talks to Postgres as the table owner and never uses Supabase's Data API.
# Close every public table to Supabase's anon/authenticated roles: RLS on with no
# policies (deny all) plus revoked grants, so the anon key can't read bookings.
LOCK_DOWN_SQL = """
DO $$
DECLARE t record;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN RETURN; END IF;
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
  END LOOP;
  REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
  REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
END $$;
"""


def lock_down_supabase(using, **kwargs):
    from django.db import connections

    connection = connections[using]
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(LOCK_DOWN_SQL)


class ComplianceConfig(AppConfig):
    name = "apps.compliance"

    def ready(self):
        # Sent once per migrate run for this app, after all apps' tables exist.
        post_migrate.connect(lock_down_supabase, sender=self)
