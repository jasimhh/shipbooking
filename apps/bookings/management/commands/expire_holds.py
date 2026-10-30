from django.core.management.base import BaseCommand

from apps.bookings.services import expire_holds


class Command(BaseCommand):
    help = "Release places held by unpaid reservations past their expiry. Run every minute from cron."

    def handle(self, *args, **options):
        self.stdout.write(f"Released {expire_holds()} expired hold(s).")
