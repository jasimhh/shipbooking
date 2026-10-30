from django.core.management.base import BaseCommand

from apps.payments import gateway, services


class Command(BaseCommand):
    help = "Check Razorpay for orders still marked created and settle any that were paid. Run every few minutes."

    def handle(self, *args, **options):
        if not gateway.is_configured():
            self.stdout.write("Razorpay is not configured; nothing to reconcile.")
            return
        self.stdout.write(f"Settled {services.reconcile()} payment(s).")
